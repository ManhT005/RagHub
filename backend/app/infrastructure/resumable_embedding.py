"""Canonical host embedding path shared by upload and inactive index rebuilds."""

from dataclasses import asdict
from uuid import uuid5

from raghub_core.domain.ingestion.chunker import embedding_text
from raghub_core.domain.ingestion.errors import IngestionError
from raghub_core.domain.ingestion.tokenizer import ENCODING

from app.infrastructure.embedding_cache import EmbeddingCache
from app.infrastructure.embedding_execution import (
    EmbeddingDeferred,
    configure_batch_provider,
    policy_for_workspace,
    resolve_policy,
)
from app.modules.ai_providers.models import EmbeddingWorkItem
from app.modules.ai_providers.work_items import (
    WorkItemProcessor,
    WorkItemRepository,
    decode_manifest,
    encode_manifest,
    manifest_key,
)


class RuntimeQuota:
    def __init__(self, runtime, quota, enabled=True):
        self.runtime, self.quota = runtime, quota
        self.enabled = enabled

    async def acquire(self, *, scope, tokens, background=True):
        if self.enabled and self.runtime.quota_scope:
            if self.quota is None:
                raise IngestionError(
                    "EMBEDDING_QUOTA_UNAVAILABLE", "Quota coordinator missing.", retryable=True
                )
            await self.quota.acquire(
                scope=self.runtime.quota_scope, tokens=tokens, background=background
            )


class DurableEmbeddingStorage:
    """Classify checkpoint I/O outages separately from invalid embedding responses."""

    def __init__(self, storage):
        self.storage = storage

    async def get(self, key):
        try:
            return await self.storage.get(key)
        except Exception as error:
            if isinstance(error, KeyError) or getattr(error, "code", None) in {
                "NoSuchKey",
                "NoSuchObject",
            }:
                raise  # A missing uncommitted artifact is the processor's cache-miss path.
            raise IngestionError(
                "STORAGE_UNAVAILABLE", "Durable embedding storage is unavailable.", retryable=True
            ) from error

    async def put(self, key, content, content_type):
        try:
            return await self.storage.put(key, content, content_type)
        except Exception as error:
            raise IngestionError(
                "STORAGE_UNAVAILABLE",
                "Durable embedding checkpoint could not be stored.",
                retryable=True,
            ) from error


def chunk_manifest(chunks):
    return [
        {
            **asdict(c),
            "chunk_id": str(c.chunk_id),
            "parent_section_id": str(c.parent_section_id) if c.parent_section_id else None,
            "previous_chunk_id": str(c.previous_chunk_id) if c.previous_chunk_id else None,
            "next_chunk_id": str(c.next_chunk_id) if c.next_chunk_id else None,
            "text": embedding_text(c),
            "tokens": len(ENCODING.encode(embedding_text(c))),
        }
        for c in chunks
    ]


class ResumableEmbedding:
    def __init__(
        self, session, storage, settings, quota=None, telemetry=None, *, defer_uploads=False
    ):
        self.session, self.storage = session, DurableEmbeddingStorage(storage)
        self.settings, self.quota = settings, quota
        self.telemetry = telemetry
        self.repository = WorkItemRepository(session, settings)
        self.defer_uploads = defer_uploads

    @staticmethod
    def identity(document, runtime):
        if not runtime.fingerprint:
            raise ValueError("Canonical embedding requires a semantic fingerprint.")
        return uuid5(document.version_id, runtime.fingerprint + ":" + runtime.index_name)

    async def execute(self, document, chunks, runtime):
        item_id = self.identity(document, runtime)
        item = await self.session.get(EmbeddingWorkItem, item_id)
        manifest = chunk_manifest(chunks)
        if item is None:
            # Persist the layout once; changing speed cannot reinterpret old checkpoints.
            from sqlalchemy.ext.asyncio import AsyncSession

            if isinstance(self.session, AsyncSession):
                policy = await policy_for_workspace(
                    self.session,
                    self.settings,
                    document.scope.workspace_id,
                    index_name=runtime.index_name,
                )
            else:
                policy = resolve_policy(self.settings, "unknown")
            key = manifest_key(document.scope.organization_id, document.scope.workspace_id, item_id)
            await self.storage.put(key, encode_manifest(manifest), "application/gzip")
            try:
                item = await self.repository.create(
                    organization_id=document.scope.organization_id,
                    workspace_id=document.scope.workspace_id,
                    kind=document.kind,
                    pool_id=None,
                    document_version_id=document.version_id,
                    total_chunks=len(chunks),
                    manifest_key=key,
                )
            except ValueError as exc:
                raise IngestionError(
                    "EMBEDDING_QUOTA_WAIT", "Workspace embedding queue full.", retryable=True
                ) from exc
            item.id = item_id
            item.embedding_fingerprint = runtime.fingerprint
            item.index_name, item.dimension = runtime.index_name, runtime.dimension
            item.execution_config = policy.snapshot()
            await self.session.commit()
        else:
            if (item.embedding_fingerprint, item.index_name, item.dimension) != (
                runtime.fingerprint,
                runtime.index_name,
                runtime.dimension,
            ):
                raise ValueError("Work-item embedding fingerprint mismatch.")
            stored = decode_manifest(await self.storage.get(item.manifest_key))
            # Additive structural metadata must not invalidate safe legacy checkpoints.
            identity_fields = ("chunk_id", "text", "tokens", "content", "content_hash")
            if [[c.get(k) for k in identity_fields] for c in stored] != [
                [c.get(k) for k in identity_fields] for c in manifest
            ]:
                raise ValueError("Document chunk manifest changed during resume.")
        if item.state == "FAILED":
            raise IngestionError(
                "EMBEDDING_WORK_ITEM_FAILED",
                "Embedding work item requires an explicit document retry.",
                retryable=False,
            )
        if self.defer_uploads and document.kind == "upload":
            from app.workers.embedding_tasks import process_work_item_batch

            try:
                process_work_item_batch.delay(str(item.id))
            except Exception as exc:
                raise IngestionError(
                    "QUEUE_UNAVAILABLE", "Embedding dispatch failed.", retryable=True
                ) from exc
            raise EmbeddingDeferred()
        policy = getattr(item, "execution_config", None) or {
            "batch_max_chunks": 24,
            "batch_target_tokens": 10000,
            "max_inflight_requests": 1,
        }
        configure_batch_provider(runtime.provider)
        collected = []

        async def finalize(_item_id, vectors):
            collected.extend(vectors)

        async def uncached(texts):
            if self.settings.rag_embedding_cache_enabled:
                from raghub_core.domain.embedding.quota import estimate_tokens

                await RuntimeQuota(runtime, self.quota).acquire(
                    scope=runtime.quota_scope or "",
                    tokens=estimate_tokens(sum(len(t) for t in texts)),
                )
            return await runtime.provider.embed_documents(texts)

        async def embed(texts):
            if self.settings.rag_embedding_cache_enabled:
                cache = EmbeddingCache(
                    self.storage,
                    document.scope.organization_id,
                    runtime.fingerprint,
                    runtime.dimension,
                    telemetry=self.telemetry,
                )
                return await cache.embed(texts, uncached)
            return await runtime.provider.embed_documents(texts)

        processor = WorkItemProcessor(
            self.repository,
            RuntimeQuota(
                runtime, self.quota, enabled=not self.settings.rag_embedding_cache_enabled
            ),
            load_blob=self.storage.get,
            store_blob=lambda key, blob: self.storage.put(key, blob, "application/gzip"),
            embed_texts=embed,
            finalize=finalize,
            dimension=runtime.dimension,
            max_chunks=policy["batch_max_chunks"],
            target_tokens=policy["batch_target_tokens"],
            max_inflight=min(
                policy["max_inflight_requests"], self.settings.rag_embedding_max_inflight_hard_cap
            ),
            complete_on_finalize=False,
            batch_hard_caps=(
                self.settings.rag_embedding_max_batch_chunks_hard_cap,
                self.settings.rag_embedding_max_batch_tokens_hard_cap,
            ),
            telemetry=self.telemetry,
        )
        if item.state in {"EMBEDDED", "COMPLETED"}:
            # Reassemble and validate immutable checkpoints, including retries after an ES failure.
            from raghub_core.domain.embedding.batching import split_batches

            batches = split_batches(
                [c["tokens"] for c in manifest],
                max_chunks=processor.max_chunks,
                target_tokens=processor.target_tokens,
            )
            await processor._finish(item, manifest, batches)
        else:
            while not collected:
                outcome = await processor.process_one(item_id)
                await self.session.commit()  # Each batch survives process loss.
                if item.state == "WAITING_QUOTA":
                    raise IngestionError(
                        "EMBEDDING_QUOTA_WAIT", "Embedding quota depleted.", retryable=True
                    )
                if not outcome.done and not outcome.embedded_chunks:
                    raise IngestionError(
                        "EMBEDDING_QUOTA_WAIT", "Workspace embedding slot busy.", retryable=True
                    )
        return collected

    async def complete(self, document, runtime):
        item = await self.session.get(EmbeddingWorkItem, self.identity(document, runtime))
        if item is not None:
            await self.repository.complete(item)
            await self.session.commit()
