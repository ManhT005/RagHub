import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.self_host import SelfHostContainer
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core_domain.documents.upload import UploadDocumentCommand
from app.core_domain.ingestion.errors import RETRYABLE_ERROR_CODES, ingestion_error_message
from app.core_domain.retrieval.models import RetrievalScope
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
        self.container = SelfHostContainer(
            session, self.settings, storage=storage, task_queue=task_queue
        )
        self.repository = self.container.documents
        self.storage = self.container.storage
        self.task_queue = self.container.queue

    async def upload(self, command: UploadDocumentCommand) -> DocumentAccepted:
        result = await self.container.upload_document().execute(command)
        return DocumentAccepted(**asdict(result))

    async def retry(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID, version_id: uuid.UUID
    ) -> DocumentAccepted:
        return await self._retry(organization_id, workspace_id, version_id, reindex=False)

    async def reindex(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID, version_id: uuid.UUID
    ) -> DocumentAccepted:
        return await self._retry(organization_id, workspace_id, version_id, reindex=True)

    async def _retry(self, organization_id, workspace_id, version_id, *, reindex):
        receipt = await self.container.retry_document().execute(
            RetrievalScope(organization_id, workspace_id), version_id, reindex=reindex
        )
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
