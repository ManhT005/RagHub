"""Resumable embedding work items: caps, checkpoints and one-batch processing.

Each worker call handles exactly one batch, then the caller requeues while
batches remain. Vector artifacts persist before the checkpoint row, so a
crash between provider response and persistence can cost quota but never
duplicates indexed data (replay skips checkpointed batches).
"""
from __future__ import annotations

import gzip
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from raghub_core.domain.embedding.batching import remaining_batches, split_batches
from raghub_core.domain.embedding.quota import estimate_tokens
from raghub_core.ports.embedding_quota import (
    EmbeddingQuotaPort,
    QuotaDepletedError,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_providers.models import (
    EmbeddingBatchCheckpoint,
    EmbeddingWorkItem,
    ProviderCredential,
    ProviderPool,
)

QUEUED = "QUEUED"
WAITING_QUOTA = "WAITING_QUOTA"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

MAX_ACTIVE_PER_WORKSPACE = 1
MAX_PENDING_PER_WORKSPACE = 5


def manifest_key(organization_id: UUID, workspace_id: UUID, item_id: UUID) -> str:
    return f"{organization_id}/{workspace_id}/embedding-manifests/{item_id}.json.gz"


def artifact_key(organization_id: UUID, workspace_id: UUID, item_id: UUID, batch: int) -> str:
    return f"{organization_id}/{workspace_id}/embedding-batches/{item_id}/{batch}.json.gz"


def encode_manifest(chunks: list[dict]) -> bytes:
    return gzip.compress(
        json.dumps({"version": 1, "chunks": chunks}, ensure_ascii=False).encode("utf-8")
    )


def decode_manifest(payload: bytes) -> list[dict]:
    data = json.loads(gzip.decompress(payload).decode("utf-8"))
    assert data.get("version") == 1
    return data["chunks"]


def encode_artifact(vectors: list[list[float]]) -> bytes:
    return gzip.compress(json.dumps({"vectors": vectors}).encode("utf-8"))


def decode_artifact(payload: bytes) -> list[list[float]]:
    return json.loads(gzip.decompress(payload).decode("utf-8"))["vectors"]


class WorkItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        pool_id: UUID,
        kind: str = "upload",
        document_version_id: UUID | None = None,
        total_chunks: int = 0,
        manifest_key: str | None = None,
    ) -> EmbeddingWorkItem:
        active = await self.session.scalar(
            select(func.count(EmbeddingWorkItem.id)).where(
                EmbeddingWorkItem.workspace_id == workspace_id,
                EmbeddingWorkItem.state.in_([QUEUED, WAITING_QUOTA, RUNNING]),
            )
        )
        pending = await self.session.scalar(
            select(func.count(EmbeddingWorkItem.id)).where(
                EmbeddingWorkItem.workspace_id == workspace_id,
                EmbeddingWorkItem.state.in_([QUEUED, WAITING_QUOTA]),
            )
        )
        if (active or 0) > MAX_ACTIVE_PER_WORKSPACE or (pending or 0) >= MAX_PENDING_PER_WORKSPACE:
            raise ValueError("Workspace embedding queue is full.")
        item = EmbeddingWorkItem(
            organization_id=organization_id,
            workspace_id=workspace_id,
            document_version_id=document_version_id,
            pool_id=pool_id,
            kind=kind,
            state=QUEUED,
            total_chunks=total_chunks,
            manifest_key=manifest_key,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def claim(
        self, item_id: UUID, *, now: datetime | None = None
    ) -> EmbeddingWorkItem | None:
        item = await self.session.get(EmbeddingWorkItem, item_id)
        if item is None or item.state == COMPLETED:
            return None
        moment = now or datetime.now(UTC)
        if item.state == WAITING_QUOTA and item.available_at and item.available_at > moment:
            return None
        item.state = RUNNING
        item.attempts += 1
        await self.session.flush()
        return item

    async def completed_batches(self, item_id: UUID) -> set[int]:
        rows = await self.session.scalars(
            select(EmbeddingBatchCheckpoint.batch_index).where(
                EmbeddingBatchCheckpoint.work_item_id == item_id
            )
        )
        return set(rows)

    async def record_batch(
        self, item: EmbeddingWorkItem, *, batch: int, start: int, end: int, artifact: str
    ) -> None:
        self.session.add(
            EmbeddingBatchCheckpoint(
                work_item_id=item.id,
                batch_index=batch,
                chunk_start=start,
                chunk_end=end,
                chunk_count=end - start,
                artifact_key=artifact,
            )
        )
        item.embedded_chunks = end
        await self.session.flush()

    async def wait_quota(self, item: EmbeddingWorkItem, available_at_ms: int) -> None:
        item.state = WAITING_QUOTA
        item.available_at = datetime.fromtimestamp(available_at_ms / 1000, tz=UTC)
        await self.session.flush()

    async def complete(self, item: EmbeddingWorkItem) -> None:
        item.state = COMPLETED
        item.embedded_chunks = item.total_chunks
        await self.session.flush()

    async def fail(self, item: EmbeddingWorkItem, code: str, message: str) -> None:
        item.state = FAILED
        item.error_code = code
        item.error_message = message
        await self.session.flush()

    async def queue_position(self, item: EmbeddingWorkItem) -> int:
        ahead = await self.session.scalar(
            select(func.count(EmbeddingWorkItem.id)).where(
                EmbeddingWorkItem.workspace_id == item.workspace_id,
                EmbeddingWorkItem.state.in_([QUEUED, WAITING_QUOTA]),
                EmbeddingWorkItem.created_at < item.created_at,
            )
        )
        return (ahead or 0) + 1

    async def pool_for(self, item: EmbeddingWorkItem) -> ProviderPool:
        pool = await self.session.get(ProviderPool, item.pool_id)
        assert pool is not None, "Work item references a missing pool."
        return pool

    async def pool_scope(self, item: EmbeddingWorkItem) -> str:
        return (await self.pool_for(item)).quota_scope

    async def checkpoint_artifact(self, item_id: UUID, batch: int) -> str | None:
        row = await self.session.scalar(
            select(EmbeddingBatchCheckpoint).where(
                EmbeddingBatchCheckpoint.work_item_id == item_id,
                EmbeddingBatchCheckpoint.batch_index == batch,
            )
        )
        return row.artifact_key if row else None

    async def credentials_for(self, pool_id: UUID) -> list:
        rows = await self.session.scalars(
            select(ProviderCredential)
            .where(ProviderCredential.pool_id == pool_id)
            .order_by(ProviderCredential.created_at)
        )
        return list(rows)


@dataclass
class BatchOutcome:
    done: bool
    embedded_chunks: int


class WorkItemProcessor:
    """Embed one batch per call with quota gate, artifact-first persistence."""

    def __init__(
        self,
        repository: WorkItemRepository,
        quota: EmbeddingQuotaPort,
        *,
        load_blob: Callable[[str], Awaitable[bytes]],
        store_blob: Callable[[str, bytes], Awaitable[None]],
        embed_texts: Callable[[list[str]], Awaitable[list[list[float]]]],
        finalize: Callable[[UUID, list[list[float]]], Awaitable[None]],
        max_chunks: int = 24,
        target_tokens: int = 10_000,
        dimension: int = 0,
    ) -> None:
        self.repository = repository
        self.quota = quota
        self.load_blob = load_blob
        self.store_blob = store_blob
        self.embed_texts = embed_texts
        self.finalize = finalize
        self.max_chunks = max_chunks
        self.target_tokens = target_tokens
        self.dimension = dimension

    async def process_one(self, item_id: UUID) -> BatchOutcome:
        item = await self.repository.claim(item_id)
        if item is None:
            return BatchOutcome(done=True, embedded_chunks=0)
        scope = await self.repository.pool_scope(item)
        raw = await self.load_blob(item.manifest_key or "")
        chunks = decode_manifest(raw)
        if item.total_chunks != len(chunks):
            item.total_chunks = len(chunks)
        token_counts = [
            max(1, c.get("tokens") or estimate_tokens(len(c.get("text", "")))) for c in chunks
        ]
        batches = split_batches(
            token_counts, max_chunks=self.max_chunks, target_tokens=self.target_tokens
        )
        done = await self.repository.completed_batches(item.id)
        todo = remaining_batches(len(batches), done)
        if not todo:
            await self._finish(item, chunks, batches)
            return BatchOutcome(done=True, embedded_chunks=item.total_chunks)
        batch = todo[0]
        start, end = batches[batch]
        texts = [chunks[i]["text"] for i in range(start, end)]
        batch_tokens = sum(token_counts[start:end])
        try:
            await self.quota.acquire(scope=scope, tokens=batch_tokens, background=True)
        except QuotaDepletedError as exc:
            await self.repository.wait_quota(item, exc.available_at_ms)
            return BatchOutcome(done=False, embedded_chunks=item.embedded_chunks)
        vectors = await self.embed_texts(texts)
        if len(vectors) != len(texts) or any(
            (self.dimension and len(v) != self.dimension)
            or not all(math.isfinite(x) for x in v)
            for v in vectors
        ):
            await self.repository.fail(
                item, "EMBEDDING_INVALID_RESPONSE", "Batch failed validation."
            )
            raise ValueError("Embedding batch failed dimension/finite validation.")
        key = artifact_key(item.organization_id, item.workspace_id, item.id, batch)
        await self.store_blob(key, encode_artifact(vectors))
        await self.repository.record_batch(item, batch=batch, start=start, end=end, artifact=key)
        left = remaining_batches(len(batches), done | {batch})
        if not left:
            await self._finish(item, chunks, batches)
            return BatchOutcome(done=True, embedded_chunks=item.total_chunks)
        item.state = QUEUED
        return BatchOutcome(done=False, embedded_chunks=item.embedded_chunks)

    async def _finish(
        self, item: EmbeddingWorkItem, chunks: list[dict], batches: list[tuple[int, int]]
    ) -> None:
        ordered: list[list[float]] = []
        for batch, (start, end) in enumerate(batches):
            key = await self.repository.checkpoint_artifact(item.id, batch)
            if key is None:
                raise ValueError(f"Missing checkpoint for batch {batch}.")
            raw = await self.load_blob(key)
            vectors = decode_artifact(raw)
            assert len(vectors) == end - start, "Checkpoint artifact diverged from manifest."
            ordered.extend(vectors)
        await self.finalize(item.id, ordered)
        await self.repository.complete(item)
