import logging
import uuid
from collections.abc import Awaitable, Callable

from raghub_core.domain.ingestion.errors import IngestionError, ingestion_error_message
from raghub_core.domain.ingestion.models import IngestionAttempt, IngestionDocument, IngestionStage
from raghub_core.domain.retrieval.models import RetrievalScope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ingestion_progress import advance_progress, advance_stage
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
    document.status = version.status = job.stage = advance_stage(job.stage, stage)
    job.progress = advance_progress(job.progress, progress)
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
        if version is None:
            logger.info("Ingestion load: document_version_id=%s not found", version_id)
            return IngestionAttempt(None, "SKIPPED", 0, reason="VERSION_MISSING")
        job = await self.session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        if version.status == DocumentStatus.FAILED:
            # Preserve the terminal status even if the job has already been removed.
            return IngestionAttempt(None, version.status, job.progress if job is not None else 0)
        if version.status == DocumentStatus.READY and job is not None and job.progress >= 100:
            # Terminal redelivery avoids loading or mutating any other entity.
            return IngestionAttempt(None, version.status, job.progress)
        document = await self.session.get(Document, version.document_id)
        if document is None:
            logger.info("Ingestion load: document not found for version_id=%s", version_id)
            return IngestionAttempt(None, "SKIPPED", 0, reason="DOCUMENT_MISSING")
        if document.deleted_at is not None:
            logger.info("Ingestion load: document deleted for version_id=%s", version_id)
            return IngestionAttempt(None, "SKIPPED", 0, reason="DOCUMENT_DELETED")
        if job is None:
            logger.info("Ingestion load: job missing for version_id=%s", version_id)
            return IngestionAttempt(None, "SKIPPED", 0, reason="JOB_MISSING")
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
        if self.job.stage == "READY" and self.job.progress < 100:
            self.document.status = self.version.status = self.job.stage = "INDEXING"
        if self.job.stage in {"QUEUED", "UPLOADED"}:
            await self.set_stage(version_id, IngestionStage.PARSING, 20)
        else:
            await self.session.commit()

    async def set_stage(self, version_id: uuid.UUID, stage: IngestionStage, progress: int) -> None:
        await _set_stage(self.session, self.document, self.version, self.job, stage, progress)

    async def expose_version(self, version_id: uuid.UUID) -> None:
        self.version.status = DocumentStatus.INDEXING
        self.job.progress = advance_progress(self.job.progress, 90)
        await self.session.commit()

    async def complete(self, version_id: uuid.UUID) -> None:
        self.job.error_code = self.job.error_message = self.job.error_details = None
        await self.set_stage(version_id, IngestionStage.READY, 100)

    async def record_failure(
        self, version_id: uuid.UUID, error: IngestionError, *, failed: bool
    ) -> None:
        if error.code != "EMBEDDING_DEFERRED":
            await self.failure(self.session, version_id, error, failed=failed)
