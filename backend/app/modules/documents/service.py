import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.self_host import SelfHostContainer
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.modules.documents.schemas import DocumentAccepted, DocumentDetail, DocumentResponse
from raghub_core.domain.documents.upload import UploadDocumentCommand
from raghub_core.domain.ingestion.errors import RETRYABLE_ERROR_CODES, ingestion_error_message
from raghub_core.domain.retrieval.models import RetrievalScope
from raghub_core.ports.object_storage import ObjectStoragePort
from raghub_core.ports.task_queue import TaskQueuePort

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
        snapshot = await self.repository.embedding_snapshot(organization_id, workspace_id)
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
                response.mime_type = getattr(version, "mime_type", None)
                response.size_bytes = getattr(version, "size_bytes", None)
                response.chunk_count = getattr(version, "chunk_count", None)
                response.indexed_at = getattr(version, "indexed_at", None)
                if snapshot and response.indexed_at:
                    response.embedding_model_id = snapshot.provider_config_id
                    response.embedding_model_name = snapshot.model
                    response.embedding_dimension = snapshot.dimension
            result.append(response)
        return result

    async def detail(self, organization_id, workspace_id, document_id):
        document = await self.repository.find_document(organization_id, workspace_id, document_id)
        if document is None:
            raise AppError("DOCUMENT_NOT_FOUND", "Document not found.", status_code=404)
        # Uses the same bounded read model as list; no Elasticsearch requests.
        rows = await self.list_documents(organization_id, workspace_id)
        version = await self.repository.latest_version(organization_id, workspace_id, document_id)
        item = next(row for row in rows if row.id == document_id)
        return DocumentDetail(**item.model_dump(), checksum=version.checksum if version else None)

    async def download(self, organization_id, workspace_id, document_id):
        document = await self.repository.find_document(organization_id, workspace_id, document_id)
        if document is None:
            raise AppError("DOCUMENT_NOT_FOUND", "Document not found.", status_code=404)
        version = await self.repository.latest_version(organization_id, workspace_id, document_id)
        if version is None:
            raise AppError("DOCUMENT_NOT_FOUND", "Document version not found.", status_code=404)
        return document.name, version.mime_type, await self.storage.get(version.storage_key)

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
