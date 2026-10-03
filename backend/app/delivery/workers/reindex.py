import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.composition.worker import WorkerContainer
from app.core.config import get_settings
from app.core_domain.ingestion.reindex import is_transient_failure
from app.core_domain.providers.errors import (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.modules.ai_providers.models import EmbeddingIndexVersion, EmbeddingReindexJob
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
            use_case = WorkerContainer(session, settings).reindex_workspace()
            await use_case.execute(job_id, fail_transient=fail_transient)
    finally:
        await engine.dispose()
