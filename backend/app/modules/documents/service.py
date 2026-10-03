import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.documents.upload_document import UploadDocumentUseCase
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core_domain.documents.upload import UploadDocumentCommand
from app.core_domain.ingestion.errors import RETRYABLE_ERROR_CODES, ingestion_error_message
from app.delivery.http.uploads import read_upload, upload_from_http
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.persistence.uploads import UploadRepositoryAdapter
from app.infrastructure.task_queue.queue import CeleryTaskQueue
from app.modules.documents.repository import DocumentRepository
from app.modules.documents.schemas import DocumentAccepted, DocumentResponse
from app.ports.object_storage import ObjectStoragePort
from app.ports.task_queue import TaskQueuePort

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        *,
        storage: ObjectStoragePort | None = None,
        task_queue: TaskQueuePort | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = DocumentRepository(session)
        self.storage: ObjectStoragePort = storage or MinioObjectStorage(self.settings)
        self.task_queue = task_queue or CeleryTaskQueue()

    async def upload(self, command: UploadDocumentCommand) -> DocumentAccepted:
        result = await UploadDocumentUseCase(
            UploadRepositoryAdapter(self.repository, self.session),
            self.storage,
            self.task_queue,
            max_size_mb=self.settings.max_upload_size_mb,
        ).execute(command)
        return DocumentAccepted(**asdict(result))

    async def upload_document(
        self, *, organization_id: uuid.UUID, workspace_id: uuid.UUID, upload
    ) -> DocumentAccepted:
        # Compatibility entry point; routers use the HTTP upload adapter directly.
        return await upload_from_http(self, organization_id, workspace_id, upload)

    async def retry(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID, version_id: uuid.UUID
    ) -> DocumentAccepted:
        result = await self.repository.find_version_for_retry(
            organization_id, workspace_id, version_id
        )
        if result is None:
            raise AppError(
                "DOCUMENT_VERSION_NOT_FOUND", "Document version was not found.", status_code=404
            )
        document, version, job = result
        if version.status != "FAILED":
            raise AppError(
                "INVALID_DOCUMENT_STATUS", "Only failed versions can be retried.", status_code=409
            )
        if job.error_code not in RETRYABLE_ERROR_CODES:
            raise AppError(
                "DOCUMENT_NOT_RETRYABLE",
                "This failure cannot be retried. Correct the document and upload it again.",
                status_code=409,
            )
        if not await self.repository.try_retry_lock(version.id):
            raise AppError(
                "INGESTION_IN_PROGRESS", "Ingestion is still finishing.", status_code=409
            )
        document.status = version.status = job.stage = "QUEUED"
        job.progress = job.attempts = 0
        job.error_code = job.error_message = job.error_details = None
        await self.session.commit()
        try:
            self.task_queue.enqueue_ingestion(version.id)
        except Exception as exc:
            logger.exception("Could not enqueue retry for document version %s", version.id)
            await self.repository.mark_queue_failure(version.id, str(exc))
            await self.session.commit()
            raise AppError(
                "QUEUE_UNAVAILABLE", "Could not queue ingestion.", status_code=503
            ) from exc
        return DocumentAccepted(
            document_id=document.id,
            document_version_id=version.id,
            job_id=job.id,
            status=version.status,
            created_at=version.created_at,
        )

    async def reindex(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID, version_id: uuid.UUID
    ) -> DocumentAccepted:
        result = await self.repository.find_version_for_retry(
            organization_id, workspace_id, version_id
        )
        if result is None:
            raise AppError(
                "DOCUMENT_VERSION_NOT_FOUND", "Document version was not found.", status_code=404
            )
        document, version, job = result
        if version.status != "READY":
            raise AppError(
                "INVALID_DOCUMENT_STATUS", "Only ready versions can be re-indexed.", status_code=409
            )
        if not await self.repository.try_retry_lock(version.id):
            raise AppError(
                "INGESTION_IN_PROGRESS", "Ingestion is still finishing.", status_code=409
            )
        document.status = version.status = job.stage = "QUEUED"
        job.progress = job.attempts = 0
        job.error_code = job.error_message = job.error_details = None
        await self.session.commit()
        try:
            self.task_queue.enqueue_ingestion(version.id)
        except Exception as exc:
            logger.exception("Could not enqueue re-index for document version %s", version.id)
            await self.repository.mark_queue_failure(version.id, str(exc))
            await self.session.commit()
            raise AppError(
                "QUEUE_UNAVAILABLE", "Could not queue re-indexing.", status_code=503
            ) from exc
        return DocumentAccepted(
            document_id=document.id,
            document_version_id=version.id,
            job_id=job.id,
            status=version.status,
            created_at=version.created_at,
        )

    async def list_documents(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[DocumentResponse]:
        if not await self.repository.workspace_exists(organization_id, workspace_id):
            raise AppError(
                "WORKSPACE_NOT_FOUND",
                "Workspace was not found in the current organization.",
                status_code=404,
            )
        documents = await self.repository.list_documents(organization_id, workspace_id)
        jobs = await self.repository.list_document_jobs(organization_id, workspace_id)
        result = []
        for document in documents:
            response = DocumentResponse.model_validate(document, from_attributes=True)
            if document.id in jobs:
                version, job = jobs[document.id]
                response.document_version_id = version.id
                response.job_id = job.id
                response.stage = job.stage
                response.progress = job.progress
                response.attempts = job.attempts
                response.error_code = job.error_code
                response.error_message = ingestion_error_message(job.error_code)
                response.retryable = (
                    version.status == "FAILED" and job.error_code in RETRYABLE_ERROR_CODES
                )
            result.append(response)
        return result

    async def delete_document(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        document = await self.repository.find_document(organization_id, workspace_id, document_id)
        if document is None:
            raise AppError(
                "DOCUMENT_NOT_FOUND", "Document was not found in this workspace.", status_code=404
            )
        document.deleted_at = datetime.now(UTC)
        await self.session.commit()

    async def _read_limited(self, upload) -> bytes:
        return await read_upload(upload, max_size_mb=self.settings.max_upload_size_mb)
