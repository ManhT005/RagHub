"""Canonical host embedding path shared by upload and inactive index rebuilds."""

from dataclasses import asdict
from uuid import uuid5

from raghub_core.domain.ingestion.errors import IngestionError

from app.infrastructure.embedding_cache import EmbeddingCache
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


def chunk_manifest(chunks):
    return [
        {**asdict(c), "chunk_id": str(c.chunk_id), "text": c.content, "tokens": c.token_count}
        for c in chunks
    ]


class ResumableEmbedding:
    def __init__(self, session, storage, settings, quota=None, telemetry=None):
        self.session, self.storage = session, storage
        self.settings, self.quota = settings, quota
        self.telemetry = telemetry
        self.repository = WorkItemRepository(session, settings)

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
            key = manifest_key(document.scope.organization_id, document.scope.workspace_id, item_id)
            await self.storage.put(key, encode_manifest(manifest), "application/gzip")
            try:
                item = await self.repository.create(
                    organization_id=document.scope.organization_id,
                    workspace_id=document.scope.workspace_id,
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
            await self.session.commit()
        else:
            if (item.embedding_fingerprint, item.index_name, item.dimension) != (
                runtime.fingerprint,
                runtime.index_name,
                runtime.dimension,
            ):
                raise ValueError("Work-item embedding fingerprint mismatch.")
            if decode_manifest(await self.storage.get(item.manifest_key)) != manifest:
                raise ValueError("Document chunk manifest changed during resume.")
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
            max_chunks=self.settings.rag_embedding_batch_max_chunks,
            target_tokens=self.settings.rag_embedding_batch_target_tokens,
            complete_on_finalize=False,
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
