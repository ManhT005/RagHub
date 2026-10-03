import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.documents.retry_document import RetryDocumentUseCase
from app.application.documents.upload_document import UploadDocumentUseCase
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core_domain.documents.upload import UploadDocumentCommand
from app.core_domain.ingestion.errors import RETRYABLE_ERROR_CODES, ingestion_error_message
from app.core_domain.retrieval.models import RetrievalScope
from app.delivery.http.uploads import read_upload, upload_from_http
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.persistence.uploads import (
    DocumentRetryRepositoryAdapter,
    UploadRepositoryAdapter,
)
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
        return await self._retry(organization_id, workspace_id, version_id, reindex=False)

    async def reindex(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID, version_id: uuid.UUID
    ) -> DocumentAccepted:
        return await self._retry(organization_id, workspace_id, version_id, reindex=True)

    async def _retry(self, organization_id, workspace_id, version_id, *, reindex):
        receipt = await RetryDocumentUseCase(
            DocumentRetryRepositoryAdapter(self.repository, self.session),
            self.task_queue,
        ).execute(RetrievalScope(organization_id, workspace_id), version_id, reindex=reindex)
        return DocumentAccepted(**asdict(receipt))

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
