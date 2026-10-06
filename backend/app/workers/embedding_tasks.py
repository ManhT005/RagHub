"""One-batch embedding worker: each task run embeds a single batch, then requeues."""

import asyncio
import uuid

from celery import Task
from raghub_core.ports.embedding_quota import QuotaBackendUnavailableError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.redis.quota_buckets import QuotaBucketStore
from app.infrastructure.task_queue.celery_app import celery_app
from app.modules.ai_providers.models import EmbeddingWorkItem
from app.modules.ai_providers.work_items import (
    WorkItemProcessor,
    WorkItemRepository,
)


async def _process_one_batch(session: AsyncSession, item_id: uuid.UUID) -> bool:
    settings = get_settings()
    repository = WorkItemRepository(session)
    redis = Redis.from_url(settings.redis_url, socket_timeout=2)
    quota = QuotaBucketStore(redis, settings)
    storage = MinioObjectStorage(settings)

    from sqlalchemy import select

    from app.infrastructure.providers import ProviderResolverAdapter
    from app.infrastructure.resumable_embedding import RuntimeQuota
    from app.modules.ai_providers.models import EmbeddingIndexVersion
    from app.modules.ai_providers.resolver import ProviderResolver

    item = await session.get(EmbeddingWorkItem, item_id)
    if item is None:
        await redis.aclose()
        return True
    if not item.index_name or not item.embedding_fingerprint:
        await redis.aclose()
        raise ValueError("Work item has no immutable embedding snapshot.")
    version = await session.scalar(
        select(EmbeddingIndexVersion).where(
            EmbeddingIndexVersion.index_name == item.index_name,
            EmbeddingIndexVersion.workspace_id == item.workspace_id,
            EmbeddingIndexVersion.organization_id == item.organization_id,
        )
    )
    if version is None:
        await redis.aclose()
        raise ValueError("Work-item index version is missing.")
    try:
        runtime = await ProviderResolverAdapter(
            ProviderResolver(session)
        ).resolve_embedding_version(version.id)
    except BaseException:
        await redis.aclose()
        raise
    if runtime.fingerprint != item.embedding_fingerprint:
        await redis.aclose()
        raise ValueError("Work-item runtime fingerprint mismatch.")

    async def finalize(item_id: uuid.UUID, vectors: list[list[float]]) -> None:
        from datetime import UTC, datetime

        from raghub_core.domain.ingestion.chunker import TextChunk
        from sqlalchemy import select

        from app.infrastructure.elasticsearch.chunks import ChunkIndexer
        from app.infrastructure.persistence.ingestion import IngestionRepositoryAdapter
        from app.modules.ai_providers.models import EmbeddingIndexVersion
        from app.modules.ai_providers.work_items import decode_manifest
        from app.modules.documents.models import Document, DocumentIndexMetadata, DocumentVersion

        item = await session.get(EmbeddingWorkItem, item_id)
        if (
            item is None
            or not item.index_name
            or not item.embedding_fingerprint
            or not item.dimension
        ):
            raise ValueError("Work item has no immutable index snapshot; cannot publish.")
        pool = await repository.pool_for(item) if item.pool_id else None
        if pool is not None and pool.fingerprint_v2 != item.embedding_fingerprint:
            raise ValueError("Work-item pool fingerprint mismatch.")
        version = await session.get(DocumentVersion, item.document_version_id)
        document = await session.get(Document, version.document_id) if version else None
        if document is None or document.deleted_at is not None:
            raise ValueError("Document is no longer available for publication.")
        manifest = decode_manifest(await storage.get(item.manifest_key))
        chunks = [
            TextChunk(
                uuid.UUID(c["chunk_id"]),
                c["chunk_index"],
                c["content"],
                c["token_count"],
                c["source_name"],
                c["page_number"],
                c["heading"],
                c["content_hash"],
                normalized_content=c.get("normalized_content"),
                embedding_content=c.get("embedding_content"),
                heading_path=tuple(c.get("heading_path") or ()),
                parent_section_id=uuid.UUID(c["parent_section_id"])
                if c.get("parent_section_id")
                else None,
                previous_chunk_id=uuid.UUID(c["previous_chunk_id"])
                if c.get("previous_chunk_id")
                else None,
                next_chunk_id=uuid.UUID(c["next_chunk_id"]) if c.get("next_chunk_id") else None,
                metadata=c.get("metadata") or {},
            )
            for c in manifest
        ]
        if len(chunks) != len(vectors) or any(len(v) != item.dimension for v in vectors):
            raise ValueError("Final vectors do not match the manifest.")
        indexer = ChunkIndexer(
            index_name=item.index_name, dimension=item.dimension, settings=settings
        )
        try:
            indexer.replace_document_version(
                organization_id=item.organization_id,
                workspace_id=item.workspace_id,
                document_id=document.id,
                document_version_id=version.id,
                source_name=document.name,
                chunks=chunks,
                embeddings={str(c.chunk_id): v for c, v in zip(chunks, vectors, strict=True)},
            )
        finally:
            indexer.close()
        index_version = await session.scalar(
            select(EmbeddingIndexVersion).where(
                EmbeddingIndexVersion.index_name == item.index_name,
                EmbeddingIndexVersion.workspace_id == item.workspace_id,
                EmbeddingIndexVersion.organization_id == item.organization_id,
            )
        )
        if index_version is None:
            raise ValueError("Index version is no longer available.")
        metadata = await session.get(DocumentIndexMetadata, (version.id, index_version.id))
        if metadata is None:
            metadata = DocumentIndexMetadata(
                document_version_id=version.id, embedding_index_version_id=index_version.id
            )
            session.add(metadata)
        metadata.chunk_count = len(chunks)
        metadata.indexed_at = datetime.now(UTC)
        if item.kind == "upload":
            ingestion = IngestionRepositoryAdapter(session)
            if await ingestion.load(version.id) is not None:
                from app.modules.documents.models import DocumentStatus

                document.status = version.status = ingestion.job.stage = DocumentStatus.READY
                ingestion.job.progress = 100
                ingestion.job.error_code = ingestion.job.error_message = (
                    ingestion.job.error_details
                ) = None
                version.chunk_count, version.indexed_at = metadata.chunk_count, metadata.indexed_at

    processor = WorkItemProcessor(
        repository,
        RuntimeQuota(runtime, quota),
        load_blob=storage.get,
        store_blob=lambda key, blob: storage.put(key, blob, "application/gzip"),
        embed_texts=runtime.provider.embed_documents,
        finalize=finalize,
        dimension=item.dimension or 0,
        max_chunks=settings.rag_embedding_batch_max_chunks,
        target_tokens=settings.rag_embedding_batch_target_tokens,
    )
    try:
        outcome = await processor.process_one(item_id)
        await session.commit()
    finally:
        await redis.aclose()
    return outcome.done


@celery_app.task(bind=True, max_retries=None, name="embedding.process_work_item_batch")
def process_work_item_batch(self: Task, work_item_id: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)

    async def run() -> bool:
        async with AsyncSession(engine) as session:
            return await _process_one_batch(session, uuid.UUID(work_item_id))

    try:
        done = asyncio.run(run())
    except QuotaBackendUnavailableError as exc:
        # Fail closed: requeue without touching the provider.
        raise self.retry(exc=exc, countdown=30) from exc
    finally:
        asyncio.run(engine.dispose())
    if not done:
        self.retry(countdown=5)
