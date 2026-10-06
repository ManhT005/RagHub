import logging
import time
import uuid

from raghub_core.domain.ingestion.errors import IngestionError
from raghub_core.domain.ingestion.models import IngestionResult
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.composition.worker import WorkerContainer
from app.core.config import get_settings
from app.infrastructure.embedding_execution import EmbeddingDeferred
from app.infrastructure.ingestion_lock import try_ingestion_lock
from app.infrastructure.persistence.ingestion import (
    _record_failure as _record_failure,
)
from app.infrastructure.persistence.ingestion import (
    _set_stage as _set_stage,
)
from app.infrastructure.redis.quota_buckets import QuotaBucketStore
from app.modules.ai_providers.models import EmbeddingIndexVersion, EmbeddingWorkItem
from app.modules.documents.models import Document, DocumentVersion, IngestionJob
from app.modules.workspaces.models import Workspace

logger = logging.getLogger(__name__)


def _make_container(session: AsyncSession) -> tuple[WorkerContainer, Redis]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, socket_timeout=2)
    return WorkerContainer(
        session, settings, quota=QuotaBucketStore(redis, settings), defer_uploads=True
    ), redis


async def _run_pipeline(
    session: AsyncSession, document: Document, version: DocumentVersion, job: IngestionJob
) -> None:
    # Broker redelivery resumes the durable item, without reading/parsing the source.
    if job.stage in {"EMBEDDING", "INDEXING"}:
        item = await session.scalar(
            select(EmbeddingWorkItem)
            .join(
                EmbeddingIndexVersion,
                EmbeddingIndexVersion.index_name == EmbeddingWorkItem.index_name,
            )
            .join(
                Workspace, Workspace.active_embedding_index_version_id == EmbeddingIndexVersion.id
            )
            .where(
                EmbeddingWorkItem.document_version_id == version.id,
                EmbeddingWorkItem.kind.in_(["upload", "recovery"]),
                EmbeddingWorkItem.state != "COMPLETED",
            )
            .order_by(EmbeddingWorkItem.created_at.desc())
            .limit(1)
        )
        if item is not None:
            from app.workers.embedding_tasks import process_work_item_batch

            if item.state == "FAILED":
                raise IngestionError(
                    "EMBEDDING_WORK_ITEM_FAILED", "Explicit retry required.", retryable=False
                )
            try:
                process_work_item_batch.delay(str(item.id))
            except Exception as exc:
                raise IngestionError(
                    "QUEUE_UNAVAILABLE", "Embedding dispatch failed.", retryable=True
                ) from exc
            raise EmbeddingDeferred()
    container, redis = _make_container(session)
    try:
        repository = container.ingestion_repository(document=document, version=version, job=job)
        await _make_use_case(session, repository, container=container).build(repository.snapshot())
    finally:
        await redis.aclose()


def _make_use_case(session, repository, *, pipeline=None, container=None):
    return (container or WorkerContainer(session)).run_ingestion(repository, pipeline=pipeline)


async def _run_attempt(
    session: AsyncSession, version_id: uuid.UUID, *, retries: int, max_retries: int
):
    repository = WorkerContainer(session).ingestion_repository(failure=_record_failure)

    async def pipeline(_document):
        await _run_pipeline(session, repository.document, repository.version, repository.job)

    try:
        return await _make_use_case(session, repository, pipeline=pipeline).execute(
            version_id, retries=retries, max_retries=max_retries
        )
    except EmbeddingDeferred:
        return IngestionResult(version_id, "EMBEDDING", False, reason="EMBEDDING_QUEUED")


async def _process_document_version(
    version_id: uuid.UUID, *, retries: int = 0, max_retries: int = 3
) -> dict[str, object]:
    started = time.monotonic()
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            async with try_ingestion_lock(connection, version_id) as acquired:
                if not acquired:
                    logger.info("Ignoring concurrent delivery for version %s", version_id)
                    return {
                        "version_id": str(version_id),
                        "status": "SKIPPED",
                        "processed": False,
                        "reason": "CONCURRENT_LOCK_HELD",
                        "duration_ms": int((time.monotonic() - started) * 1000),
                    }
                # The session and lock share a pinned connection. Commits cannot release the lock.
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    result = await _run_attempt(
                        session, version_id, retries=retries, max_retries=max_retries
                    )
                    duration_ms = int((time.monotonic() - started) * 1000)
                    logger.info(
                        "Ingestion complete: document_version_id=%s status=%s processed=%s "
                        "reason=%s attempt=%d duration_ms=%d",
                        version_id,
                        result.status,
                        result.processed,
                        result.reason,
                        retries,
                        duration_ms,
                    )
                    return {
                        "version_id": str(result.version_id),
                        "status": str(result.status),
                        "processed": result.processed,
                        "reason": result.reason,
                        "duration_ms": duration_ms,
                    }
    finally:
        await engine.dispose()
