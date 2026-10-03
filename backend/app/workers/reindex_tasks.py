import asyncio
import logging
import uuid

from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.application.ingestion.build_document_index import BuildDocumentIndexUseCase
from app.application.ingestion.reindex_workspace import ReindexWorkspaceUseCase
from app.core.config import get_settings
from app.core_domain.ingestion.reindex import is_transient_failure
from app.core_domain.providers.errors import (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.infrastructure.elasticsearch.chunks import ChunkIndexer
from app.infrastructure.elasticsearch.vector_store import LegacyVectorStoreAdapter
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.persistence.reindex import ReindexRepositoryAdapter
from app.infrastructure.providers import ProviderResolverAdapter
from app.infrastructure.task_queue.celery_app import celery_app
from app.modules.ai_providers.models import EmbeddingIndexVersion, EmbeddingReindexJob
from app.modules.ai_providers.resolver import ProviderResolver
from app.modules.ingestion.parser import parse_document
from app.modules.workspaces.models import Workspace

logger = logging.getLogger(__name__)


def _is_current_target(workspace: Workspace, version: EmbeddingIndexVersion) -> bool:
    return workspace.pending_embedding_index_version_id == version.id


def _has_all_document_versions(expected: set[uuid.UUID], indexed: set[uuid.UUID]) -> bool:
    return expected.issubset(indexed)


def _is_transient_error(exc: Exception) -> bool:
    if is_transient_failure(exc):
        return True
    if isinstance(
        exc,
        ProviderTimeoutError
        | ProviderUnavailableError
        | ProviderRateLimitError
        | ConnectionError
        | TimeoutError,
    ):
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status in {429, 502, 503, 504}:
        return True
    return exc.__class__.__module__.split(".")[0] in {"elastic_transport", "urllib3"}


def _reset_attempt_progress(job: EmbeddingReindexJob, total_documents: int) -> None:
    job.total_documents = total_documents
    job.processed_documents = 0
    job.failed_documents = 0


async def _run_reindex(job_id: uuid.UUID, *, fail_transient: bool = False) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            repository = ReindexRepositoryAdapter(session)
            builder = BuildDocumentIndexUseCase(MinioObjectStorage(settings), parse_document)

            def make_store(runtime):
                return LegacyVectorStoreAdapter(
                    ChunkIndexer(
                        settings=settings,
                        index_name=runtime.index_name,
                        dimension=runtime.dimension,
                    )
                )

            use_case = ReindexWorkspaceUseCase(
                repository,
                builder,
                ProviderResolverAdapter(ProviderResolver(session)),
                make_store,
            )
            await use_case.execute(job_id, fail_transient=fail_transient)
    finally:
        await engine.dispose()


@celery_app.task(bind=True, max_retries=3, name="providers.reindex_workspace")
def reindex_workspace(self: Task, job_id: str) -> None:
    try:
        asyncio.run(
            _run_reindex(uuid.UUID(job_id), fail_transient=self.request.retries >= self.max_retries)
        )
    except Exception as exc:
        if _is_transient_error(exc) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=min(60, 2 ** (self.request.retries + 1))) from exc
        raise
