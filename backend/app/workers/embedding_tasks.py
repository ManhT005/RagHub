"""One-batch embedding worker: each task run embeds a single batch, then requeues."""

import asyncio
import uuid

from celery import Task
from raghub_core.domain.ingestion.errors import IngestionError
from raghub_core.domain.providers.errors import (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
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
    try:
        quota = QuotaBucketStore(redis, settings)
        from app.infrastructure.resumable_embedding import DurableEmbeddingStorage

        storage = DurableEmbeddingStorage(MinioObjectStorage(settings))

        from sqlalchemy import select

        from app.infrastructure.providers import ProviderResolverAdapter
        from app.infrastructure.resumable_embedding import RuntimeQuota
        from app.modules.ai_providers.models import EmbeddingIndexVersion
        from app.modules.ai_providers.resolver import ProviderResolver

        item = await session.get(EmbeddingWorkItem, item_id)
        if item is None:
            return True
        if item.state in {"COMPLETED", "FAILED"}:
            return True
        if item.state in {"RUNNING", "VERIFYING", "EMBEDDED"}:
            item.state = "QUEUED"  # Only called while the pinned advisory lock is held.
            await session.flush()
        if not item.index_name or not item.embedding_fingerprint:
            raise ValueError("Work item has no immutable embedding snapshot.")
        version = await session.scalar(
            select(EmbeddingIndexVersion).where(
                EmbeddingIndexVersion.index_name == item.index_name,
                EmbeddingIndexVersion.workspace_id == item.workspace_id,
                EmbeddingIndexVersion.organization_id == item.organization_id,
            )
        )
        if version is None:
            raise ValueError("Work-item index version is missing.")
        try:
            runtime = await ProviderResolverAdapter(
                ProviderResolver(session)
            ).resolve_embedding_version(version.id)
        except BaseException:
            raise
        if runtime.fingerprint != item.embedding_fingerprint:
            raise ValueError("Work-item runtime fingerprint mismatch.")

        index_version_id = version.id
        from app.infrastructure.embedding_cache import EmbeddingCache
        from app.infrastructure.embedding_execution import (
            configure_batch_provider,
            policy_for_workspace,
        )
        from app.infrastructure.telemetry.adapter import LoggingTelemetry

        effective = await policy_for_workspace(
            session, settings, item.workspace_id, index_name=item.index_name
        )
        policy = item.execution_config or {
            "batch_max_chunks": settings.rag_embedding_batch_max_chunks or 24,
            "batch_target_tokens": settings.rag_embedding_batch_target_tokens or 10000,
            "max_inflight_requests": 1,
        }
        if not item.execution_config:
            item.execution_config = policy
            await session.commit()
        configure_batch_provider(runtime.provider)
        telemetry = LoggingTelemetry()

        async def embed_uncached(texts):
            if settings.rag_embedding_cache_enabled:
                from raghub_core.domain.ingestion.tokenizer import ENCODING

                await RuntimeQuota(runtime, quota).acquire(
                    scope=runtime.quota_scope or "",
                    tokens=sum(len(ENCODING.encode(t)) for t in texts),
                )
            return await runtime.provider.embed_documents(texts)

        async def embed(texts):
            if settings.rag_embedding_cache_enabled:
                return await EmbeddingCache(
                    storage,
                    item.organization_id,
                    runtime.fingerprint,
                    runtime.dimension,
                    telemetry=telemetry,
                ).embed(texts, embed_uncached)
            return await embed_uncached(texts)

        async def finalize(item_id: uuid.UUID, vectors: list[list[float]]) -> None:
            from datetime import UTC, datetime

            from raghub_core.domain.ingestion.chunker import TextChunk
            from sqlalchemy import select

            from app.infrastructure.elasticsearch.chunks import ChunkIndexer
            from app.modules.ai_providers.models import EmbeddingIndexVersion
            from app.modules.ai_providers.work_items import decode_manifest
            from app.modules.documents.models import (
                Document,
                DocumentIndexMetadata,
                DocumentVersion,
            )

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
            from app.infrastructure.persistence.ingestion import _set_stage
            from app.modules.documents.models import IngestionJob
            from app.modules.workspaces.models import Workspace

            workspace = await session.get(Workspace, item.workspace_id)
            if item.kind in {"upload", "recovery"}:
                if workspace.active_embedding_index_version_id != index_version_id:
                    raise ValueError("Embedding target changed; explicit retry required")
                job = await session.scalar(
                    select(IngestionJob).where(IngestionJob.document_version_id == version.id)
                )
                if version.status == "FAILED" or job is None:
                    raise ValueError("Document is no longer ingestible")
                await _set_stage(session, document, version, job, "INDEXING", 85)
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
            except Exception as exc:
                raise IngestionError(
                    "INDEX_UNAVAILABLE", "Search indexing unavailable.", retryable=True
                ) from exc
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
            if item.kind in {"upload", "recovery"}:
                document.status = version.status = job.stage = "READY"
                job.progress = 100
                job.error_code = job.error_message = job.error_details = None
                version.chunk_count, version.indexed_at = metadata.chunk_count, metadata.indexed_at

        processor = WorkItemProcessor(
            repository,
            RuntimeQuota(runtime, quota, enabled=not settings.rag_embedding_cache_enabled),
            load_blob=storage.get,
            store_blob=lambda key, blob: storage.put(key, blob, "application/gzip"),
            embed_texts=embed,
            finalize=finalize,
            dimension=item.dimension or 0,
            max_chunks=policy["batch_max_chunks"],
            target_tokens=policy["batch_target_tokens"],
            max_inflight=min(policy["max_inflight_requests"], effective.max_inflight_requests),
            telemetry=telemetry,
            labels={"provider_type": effective.provider_type, "speed_profile": effective.profile},
            batch_hard_caps=(
                settings.rag_embedding_max_batch_chunks_hard_cap,
                settings.rag_embedding_max_batch_tokens_hard_cap,
            ),
        )
        outcome = await processor.process_one(item_id)
        await session.commit()
        return outcome.done

    finally:
        await redis.aclose()


async def _run_locked(session, item_id):
    from datetime import UTC, datetime, timedelta

    from app.infrastructure.persistence.ingestion import _record_failure
    from app.modules.ai_providers.work_items import WorkItemRepository

    item = await session.get(EmbeddingWorkItem, item_id)
    if item is None or item.state in {"COMPLETED", "FAILED"}:
        return True, 0
    now = datetime.now(UTC)
    if item.available_at and item.available_at > now:
        return False, max(2, (item.available_at - now).total_seconds())
    try:
        previous_chunks = item.embedded_chunks
        done = await _process_one_batch(session, item_id)
        if done:
            return True, 0
        if item.state == "WAITING_QUOTA":
            item.error_code = "WAITING_FOR_QUOTA"
            config = dict(item.execution_config or {})
            config["quota_wait_count"] = config.get("quota_wait_count", 0) + 1
            item.execution_config = config
            if config["quota_wait_count"] >= 48:
                raise IngestionError(
                    "EMBEDDING_UNAVAILABLE", "Quota wait budget exhausted.", retryable=False
                )
        await session.commit()
        return False, max(2, (item.available_at - datetime.now(UTC)).total_seconds()) if (
            item.available_at
        ) else (0 if item.embedded_chunks > previous_chunks else 2)
    except Exception as exc:
        config = dict(item.execution_config or {})
        retryable = isinstance(
            exc,
            ProviderRateLimitError
            | ProviderTimeoutError
            | ProviderUnavailableError
            | QuotaBackendUnavailableError,
        ) or (isinstance(exc, IngestionError) and exc.retryable)
        config["retry_count"] = config.get("retry_count", 0) + 1
        retry_counts = dict(config.get("batch_retry_counts") or {})
        retry_key = str(getattr(exc, "embedding_batch_index", "finalize"))
        retry_counts[retry_key] = retry_counts.get(retry_key, 0) + 1
        config["batch_retry_counts"] = retry_counts
        item.execution_config = config
        retryable = retryable and retry_counts[retry_key] < config.get("retry_max_attempts", 8)
        if not retryable:
            await WorkItemRepository(session).fail(
                item, "EMBEDDING_WORK_ITEM_FAILED", "Embedding failed."
            )
            await session.commit()
            if item.document_version_id and item.kind in {"upload", "recovery"}:
                error = IngestionError(
                    "EMBEDDING_WORK_ITEM_FAILED", "Embedding failed.", retryable=False
                )
                await _record_failure(session, item.document_version_id, error, failed=True)
            raise
        if isinstance(exc, ProviderRateLimitError):
            reason, state = "PROVIDER_RATE_LIMIT", "WAITING_QUOTA"
        elif isinstance(exc, QuotaBackendUnavailableError):
            reason, state = "QUOTA_COORDINATOR_UNAVAILABLE", "WAITING_QUOTA"
        elif isinstance(exc, ProviderTimeoutError):
            reason, state = "PROVIDER_TIMEOUT_RETRY", "RETRYING"
        elif isinstance(exc, IngestionError) and exc.code in {
            "STORAGE_UNAVAILABLE",
            "INDEX_UNAVAILABLE",
        }:
            reason, state = exc.code, "RETRYING"
        else:
            reason, state = "WAITING_FOR_PROVIDER", "WAITING_PROVIDER"
        delay = min(
            120,
            max(
                2,
                getattr(exc, "details", {}).get("retry_after_seconds")
                or config.get("retry_delay_seconds", 10),
            ),
        )
        item.state, item.error_code = state, reason
        item.error_message = None
        item.available_at = datetime.now(UTC) + timedelta(seconds=delay)
        await session.commit()
        from app.infrastructure.telemetry.adapter import LoggingTelemetry

        metrics = LoggingTelemetry()
        metrics.counter("embedding_retry_total", {})
        if reason == "PROVIDER_RATE_LIMIT":
            metrics.counter("embedding_rate_limit_total", {})
        return False, delay


async def _run_delivery(work_item_id):
    from contextlib import AsyncExitStack

    from sqlalchemy import select

    from app.infrastructure.ingestion_lock import try_ingestion_lock

    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    item_id = uuid.UUID(work_item_id)
    try:
        async with engine.connect() as connection:
            async with AsyncExitStack() as locks:
                if not await locks.enter_async_context(try_ingestion_lock(connection, item_id)):
                    return False, 2
                document_id = await connection.scalar(
                    select(EmbeddingWorkItem.document_version_id).where(
                        EmbeddingWorkItem.id == item_id
                    )
                )
                if document_id is not None and document_id != item_id:
                    if not await locks.enter_async_context(
                        try_ingestion_lock(connection, document_id)
                    ):
                        return False, 2
                else:
                    await connection.commit()
                # Lock acquisition commits the connection. Construct the session only
                # afterwards so external commits cannot invalidate an ORM transaction.
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    return await _run_locked(session, item_id)
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True, max_retries=3, reject_on_worker_lost=True, name="embedding.process_work_item_batch"
)
def process_work_item_batch(self: Task, work_item_id: str) -> None:
    done, delay = asyncio.run(_run_delivery(work_item_id))
    if not done:
        try:
            process_work_item_batch.apply_async(args=[work_item_id], countdown=delay, priority=2)
        except Exception as exc:
            raise self.retry(exc=exc, countdown=5) from exc
