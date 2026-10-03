import logging
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core_domain.ingestion.errors import IngestionError, ingestion_error_message
from app.core_domain.ingestion.models import IngestionAttempt, IngestionDocument, IngestionStage
from app.core_domain.retrieval.models import RetrievalScope
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion, IngestionJob

logger = logging.getLogger(__name__)


async def _set_stage(
    session: AsyncSession,
    document: Document,
    version: DocumentVersion,
    job: IngestionJob,
    stage: DocumentStatus,
    progress: int,
) -> None:
    document.status = version.status = job.stage = stage
    job.progress = progress
    await session.commit()


async def _record_failure(
    session: AsyncSession, version_id: uuid.UUID, error: IngestionError, *, failed: bool
) -> None:
    await session.rollback()
    version = await session.get(DocumentVersion, version_id)
    job = await session.scalar(
        select(IngestionJob).where(IngestionJob.document_version_id == version_id)
    )
    if version is None or job is None:
        return
    job.error_code = error.code
    job.error_message = ingestion_error_message(error.code)
    job.error_details = {"stage": job.stage, "retryable": error.retryable}
    if failed:
        document = await session.get(Document, version.document_id)
        version.status = job.stage = DocumentStatus.FAILED
        if document is not None:
            document.status = DocumentStatus.FAILED
    await session.commit()


class IngestionRepositoryAdapter:
    def __init__(
        self,
        session: AsyncSession,
        *,
        document=None,
        version=None,
        job=None,
        failure: Callable[..., Awaitable[None]] | None = None,
    ) -> None:
        self.session = session
        self.document, self.version, self.job = document, version, job
        self.failure = failure or _record_failure

    async def load(self, version_id: uuid.UUID) -> IngestionAttempt | None:
        version = await self.session.get(DocumentVersion, version_id)
        if version is None or version.status == DocumentStatus.FAILED:
            return None
        job = await self.session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        if version.status == DocumentStatus.READY and job is not None and job.progress >= 100:
            # Terminal redelivery avoids loading or mutating any other entity.
            return IngestionAttempt(None, version.status, job.progress)
        document = await self.session.get(Document, version.document_id)
        if document is None or document.deleted_at is not None or job is None:
            return None
        self.document, self.version, self.job = document, version, job
        return IngestionAttempt(self.snapshot(), version.status, job.progress)

    def snapshot(self) -> IngestionDocument:
        return IngestionDocument(
            RetrievalScope(self.version.organization_id, self.version.workspace_id),
            self.document.id,
            self.version.id,
            self.version.storage_key,
            self.document.name,
        )

    async def begin(self, version_id: uuid.UUID) -> None:
        self.job.attempts += 1
        self.job.error_code = self.job.error_message = self.job.error_details = None
        await self.set_stage(version_id, IngestionStage.PARSING, 20)

    async def set_stage(self, version_id: uuid.UUID, stage: IngestionStage, progress: int) -> None:
        await _set_stage(self.session, self.document, self.version, self.job, stage, progress)

    async def expose_version(self, version_id: uuid.UUID) -> None:
        self.version.status = DocumentStatus.READY
        self.job.progress = 90
        await self.session.commit()

    async def complete(self, version_id: uuid.UUID) -> None:
        self.job.error_code = self.job.error_message = self.job.error_details = None
        await self.set_stage(version_id, IngestionStage.READY, 100)

    async def record_failure(
        self, version_id: uuid.UUID, error: IngestionError, *, failed: bool
    ) -> None:
        await self.failure(self.session, version_id, error, failed=failed)
