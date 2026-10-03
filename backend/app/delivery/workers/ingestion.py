import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.composition.worker import WorkerContainer
from app.core.config import get_settings
from app.infrastructure.ingestion_lock import try_ingestion_lock
from app.infrastructure.persistence.ingestion import (
    _record_failure as _record_failure,
)
from app.infrastructure.persistence.ingestion import (
    _set_stage as _set_stage,
)
from app.modules.documents.models import Document, DocumentVersion, IngestionJob

logger = logging.getLogger(__name__)


async def _run_pipeline(
    session: AsyncSession, document: Document, version: DocumentVersion, job: IngestionJob
) -> None:
    repository = WorkerContainer(session).ingestion_repository(
        document=document, version=version, job=job
    )
    await _make_use_case(session, repository).build(repository.snapshot())


def _make_use_case(session, repository, *, pipeline=None):
    return WorkerContainer(session).run_ingestion(repository, pipeline=pipeline)


async def _run_attempt(
    session: AsyncSession, version_id: uuid.UUID, *, retries: int, max_retries: int
) -> None:
    repository = WorkerContainer(session).ingestion_repository(failure=_record_failure)

    async def pipeline(_document):
        await _run_pipeline(session, repository.document, repository.version, repository.job)

    await _make_use_case(session, repository, pipeline=pipeline).execute(
        version_id, retries=retries, max_retries=max_retries
    )


async def _process_document_version(
    version_id: uuid.UUID, *, retries: int = 0, max_retries: int = 3
) -> None:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            async with try_ingestion_lock(connection, version_id) as acquired:
                if not acquired:
                    logger.info("Ignoring concurrent delivery for version %s", version_id)
                    return
                # The session and lock share a pinned connection. Commits cannot release the lock.
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    await _run_attempt(
                        session, version_id, retries=retries, max_retries=max_retries
                    )
    finally:
        await engine.dispose()
