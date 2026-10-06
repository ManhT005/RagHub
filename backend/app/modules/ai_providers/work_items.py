"""Resumable embedding work items: caps, checkpoints and one-batch processing.

Each worker call handles exactly one batch, then the caller requeues while
batches remain. Vector artifacts persist before the checkpoint row, so a
crash between provider response and persistence can cost quota but never
duplicates indexed data (replay skips checkpointed batches).
"""

from __future__ import annotations

import asyncio
import gzip
import json
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from raghub_core.domain.embedding.batching import remaining_batches, split_batches
from raghub_core.domain.embedding.quota import estimate_tokens
from raghub_core.domain.embedding.scheduler import KIND_PRIORITY
from raghub_core.ports.embedding_quota import (
    EmbeddingQuotaPort,
    QuotaDepletedError,
)
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.ingestion_progress import advance_progress
from app.modules.ai_providers.models import (
    EmbeddingBatchCheckpoint,
    EmbeddingWorkItem,
    ProviderCredential,
    ProviderPool,
)
from app.modules.workspaces.models import Workspace

QUEUED = "QUEUED"
WAITING_QUOTA = "WAITING_QUOTA"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"


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
    def __init__(self, session: AsyncSession, settings=None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def create(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        pool_id: UUID | None,
        kind: str = "upload",
        document_version_id: UUID | None = None,
        total_chunks: int = 0,
        manifest_key: str | None = None,
    ) -> EmbeddingWorkItem:
        # Serialize admission and claims for a workspace in the current transaction.
        await self.session.scalar(
            select(Workspace.id)
            .where(Workspace.id == workspace_id, Workspace.organization_id == organization_id)
            .with_for_update()
        )
        pending = await self.session.scalar(
            select(func.count(EmbeddingWorkItem.id)).where(
                EmbeddingWorkItem.workspace_id == workspace_id,
                EmbeddingWorkItem.state.in_(
                    [QUEUED, WAITING_QUOTA, "RETRYING", "WAITING_PROVIDER"]
                ),
            )
        )
        limit = self.settings.provider_pool_max_pending_jobs_per_workspace
        if kind == "reindex" and limit > 1:
            limit -= 1  # Keep one pending slot available for foreground uploads.
        if (pending or 0) >= limit:
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
        if document_version_id and kind in {"upload", "recovery"}:
            from app.modules.documents.models import IngestionJob

            job = await self.session.scalar(
                select(IngestionJob).where(IngestionJob.document_version_id == document_version_id)
            )
            if job is not None:
                job.total_chunks = total_chunks
                job.embedded_chunks = job.embedded_chunks or 0
        return item

    async def claim(
        self, item_id: UUID, *, now: datetime | None = None
    ) -> EmbeddingWorkItem | None:
        moment = now or datetime.now(UTC)
        workspace_id = await self.session.scalar(
            select(EmbeddingWorkItem.workspace_id).where(EmbeddingWorkItem.id == item_id)
        )
        if workspace_id is None:
            return None
        workspace = await self.session.scalar(
            select(Workspace.id)
            .where(Workspace.id == workspace_id)
            .with_for_update(skip_locked=True)
        )
        if workspace is None:
            return None
        active = await self.session.scalar(
            select(func.count(EmbeddingWorkItem.id)).where(
                EmbeddingWorkItem.workspace_id == workspace_id, EmbeddingWorkItem.state == RUNNING
            )
        )
        if (active or 0) >= self.settings.provider_pool_max_active_jobs_per_workspace:
            return None
        item = await self.session.scalar(
            select(EmbeddingWorkItem)
            .where(
                EmbeddingWorkItem.id == item_id,
                EmbeddingWorkItem.state.in_(
                    [QUEUED, WAITING_QUOTA, "RETRYING", "WAITING_PROVIDER"]
                ),
                or_(
                    EmbeddingWorkItem.available_at.is_(None),
                    EmbeddingWorkItem.available_at <= moment,
                ),
            )
            .with_for_update(skip_locked=True)
        )
        if item is None:
            return None
        priority = case(KIND_PRIORITY, value=EmbeddingWorkItem.kind, else_=99)
        ahead = await self.session.scalar(
            select(EmbeddingWorkItem.id)
            .where(
                EmbeddingWorkItem.workspace_id == workspace_id,
                EmbeddingWorkItem.state.in_(
                    [QUEUED, WAITING_QUOTA, "RETRYING", "WAITING_PROVIDER"]
                ),
                or_(
                    EmbeddingWorkItem.available_at.is_(None),
                    EmbeddingWorkItem.available_at <= moment,
                ),
                priority < KIND_PRIORITY.get(item.kind, 99),
            )
            .limit(1)
        )
        if ahead is not None:
            return None
        item.state = RUNNING
        item.available_at = None
        item.attempts += 1
        await self.session.flush()
        return item

    async def terminal(self, item_id: UUID) -> bool:
        state = await self.session.scalar(
            select(EmbeddingWorkItem.state).where(EmbeddingWorkItem.id == item_id)
        )
        return state is None or state in {COMPLETED, FAILED}

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
        await self.session.flush()
        completed = await self.session.scalar(
            select(func.sum(EmbeddingBatchCheckpoint.chunk_count)).where(
                EmbeddingBatchCheckpoint.work_item_id == item.id
            )
        )
        item.embedded_chunks = min(item.total_chunks, completed or 0)
        if item.document_version_id:
            from app.modules.documents.models import IngestionJob

            job = await self.session.scalar(
                select(IngestionJob).where(
                    IngestionJob.document_version_id == item.document_version_id
                )
            )
            if job is not None:
                job.embedded_chunks = max(job.embedded_chunks or 0, item.embedded_chunks)
                job.total_chunks = item.total_chunks
                progress = min(84, 65 + int(19 * item.embedded_chunks / max(1, item.total_chunks)))
                job.progress = advance_progress(job.progress, progress)
        await self.session.flush()

    async def wait_quota(self, item: EmbeddingWorkItem, available_at_ms: int) -> None:
        item.state = WAITING_QUOTA
        item.available_at = datetime.fromtimestamp(available_at_ms / 1000, tz=UTC)
        await self.session.flush()

    async def commit(self):
        await self.session.commit()

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
                EmbeddingWorkItem.state.in_(
                    [QUEUED, WAITING_QUOTA, "RETRYING", "WAITING_PROVIDER"]
                ),
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
        complete_on_finalize: bool = True,
        telemetry=None,
        max_inflight: int = 1,
        labels=None,
        batch_hard_caps=None,
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
        self.complete_on_finalize = complete_on_finalize
        self.telemetry = telemetry
        self.max_inflight = max(1, max_inflight)
        self.labels = labels or {}
        self.batch_hard_caps = batch_hard_caps

    async def process_one(self, item_id: UUID) -> BatchOutcome:
        item = await self.repository.claim(item_id)
        if item is None:
            terminal = getattr(self.repository, "terminal", None)
            return BatchOutcome(
                done=await terminal(item_id) if terminal else False, embedded_chunks=0
            )
        try:
            return await self._process_claimed(item)
        except BaseException:
            # The host may commit ingestion failure details in this transaction.
            # Never persist RUNNING after a failed batch; durable artifacts remain reusable.
            if item.state in {RUNNING, "VERIFYING"}:
                item.state = QUEUED
                commit = getattr(self.repository, "commit", None)
                if commit:
                    await commit()
            raise

    async def _process_claimed(self, item) -> BatchOutcome:
        scope = await self.repository.pool_scope(item) if getattr(item, "pool_id", None) else ""
        raw = await self.load_blob(item.manifest_key or "")
        chunks = decode_manifest(raw)
        if item.total_chunks != len(chunks):
            raise ValueError("Work-item manifest count mismatch.")
        token_counts = [
            max(1, c.get("tokens") or estimate_tokens(len(c.get("text", "")))) for c in chunks
        ]
        batches = split_batches(
            token_counts, max_chunks=self.max_chunks, target_tokens=self.target_tokens
        )
        if self.batch_hard_caps and any(
            end - start > self.batch_hard_caps[0]
            or sum(token_counts[start:end]) > self.batch_hard_caps[1]
            for start, end in batches
        ):
            raise ValueError("Persisted batch layout exceeds current host hard caps.")
        done = await self.repository.completed_batches(item.id)
        todo = remaining_batches(len(batches), done)
        if not todo:
            await self._finish(item, chunks, batches)
            return BatchOutcome(done=True, embedded_chunks=item.total_chunks)
        selected = todo[: self.max_inflight]
        calls = [
            asyncio.create_task(
                self._embed_batch(item, chunks, batches, token_counts, batch, scope)
            )
            for batch in selected
        ]
        errors = []
        try:
            for future in asyncio.as_completed(calls):
                batch, vectors, error = await future
                if error is not None:
                    errors.append(error)
                    continue
                start, end = batches[batch]
                key = artifact_key(item.organization_id, item.workspace_id, item.id, batch)
                await self.repository.record_batch(
                    item, batch=batch, start=start, end=end, artifact=key
                )
                done.add(batch)
                item.embedded_chunks = sum(batches[i][1] - batches[i][0] for i in done)
                commit = getattr(self.repository, "commit", None)
                if commit:
                    await commit()
        finally:
            for call in calls:
                if not call.done():
                    call.cancel()
            await asyncio.gather(*calls, return_exceptions=True)
        if errors:
            terminal = [e for e in errors if not isinstance(e, QuotaDepletedError)]
            if terminal:
                if isinstance(terminal[0], ValueError):
                    await self.repository.fail(item, "EMBEDDING_INVALID_RESPONSE", "Batch invalid.")
                raise terminal[0]
            await self.repository.wait_quota(item, max(e.available_at_ms for e in errors))
            return BatchOutcome(done=False, embedded_chunks=item.embedded_chunks)
        if not remaining_batches(len(batches), done):
            item.state = "VERIFYING"
            await self._finish(item, chunks, batches)
            return BatchOutcome(done=True, embedded_chunks=item.total_chunks)
        item.state = QUEUED
        return BatchOutcome(done=False, embedded_chunks=item.embedded_chunks)

    async def _embed_batch(self, item, chunks, batches, token_counts, batch, scope):
        start, end = batches[batch]
        texts = [chunks[i]["text"] for i in range(start, end)]
        key = artifact_key(item.organization_id, item.workspace_id, item.id, batch)
        try:
            try:
                vectors = decode_artifact(await self.load_blob(key))
                if self.telemetry:
                    self.telemetry.counter("embedding_checkpoint_resume_total", self.labels)
            except Exception as exc:
                if not isinstance(exc, KeyError) and getattr(exc, "code", None) not in {
                    "NoSuchKey",
                    "NoSuchObject",
                }:
                    raise
                await self.quota.acquire(
                    scope=scope, tokens=sum(token_counts[start:end]), background=True
                )
                mark = time.perf_counter()
                if self.telemetry:
                    self.telemetry.counter("embedding_inflight_requests", self.labels, 1)
                try:
                    vectors = await self.embed_texts(texts)
                finally:
                    if self.telemetry:
                        self.telemetry.counter("embedding_inflight_requests", self.labels, -1)
                        self.telemetry.timing(
                            "embedding_batch_latency_ms",
                            (time.perf_counter() - mark) * 1000,
                            self.labels,
                        )
                if self.telemetry:
                    self.telemetry.counter("embedding_batches_total", self.labels)
            if len(vectors) != len(texts) or any(
                not v
                or (self.dimension and len(v) != self.dimension)
                or not all(math.isfinite(x) for x in v)
                for v in vectors
            ):
                raise ValueError("Embedding batch failed dimension/finite validation.")
            await self.store_blob(key, encode_artifact(vectors))
            return batch, vectors, None
        except Exception as exc:
            exc.embedding_batch_index = batch
            return batch, None, exc

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
            if len(vectors) != end - start or any(
                (self.dimension and len(vector) != self.dimension)
                or not vector
                or not all(math.isfinite(x) for x in vector)
                for vector in vectors
            ):
                raise ValueError("Checkpoint artifact diverged from manifest or dimension.")
            ordered.extend(vectors)
        await self.finalize(item.id, ordered)
        if self.telemetry is not None and getattr(item, "created_at", None):
            self.telemetry.timing(
                "embedding_document_duration_ms",
                (datetime.now(UTC) - item.created_at).total_seconds() * 1000,
                self.labels,
            )
        if self.complete_on_finalize:
            await self.repository.complete(item)
        else:
            item.state = "EMBEDDED"
