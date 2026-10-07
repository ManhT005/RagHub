import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from raghub_core.domain.documents.upload import UploadDocumentCommand
from raghub_core.domain.ingestion.errors import RETRYABLE_ERROR_CODES, ingestion_error_message
from raghub_core.domain.retrieval.models import RetrievalScope
from raghub_core.ports.object_storage import ObjectStoragePort
from raghub_core.ports.task_queue import TaskQueuePort
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.self_host import SelfHostContainer
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.modules.documents.schemas import DocumentAccepted, DocumentDetail, DocumentResponse

logger = logging.getLogger(__name__)


def attach_work_state(response, job, item=None):
    response.work_state = "QUEUED" if job.stage == "QUEUED" else "RUNNING"
    response.waiting_reason = "WAITING_FOR_WORKER" if job.stage == "QUEUED" else None
    response.embedded_chunks = getattr(job, "embedded_chunks", None)
    response.total_chunks = getattr(job, "total_chunks", None)
    if item is not None:
        response.embedded_chunks = max(response.embedded_chunks or 0, item.embedded_chunks)
        response.total_chunks = item.total_chunks
        response.work_state = item.state
        if item.state in {"WAITING_QUOTA", "WAITING_PROVIDER", "RETRYING"}:
            response.waiting_reason = item.error_code or "WAITING_FOR_QUOTA"
            response.retry_at = item.available_at
        elif item.state == "QUEUED":
            response.waiting_reason = "WAITING_FOR_WORKER"
        elif item.state == "EMBEDDED":
            response.work_state = "VERIFYING"
    if job.stage in {"READY", "FAILED"}:
        response.work_state = "COMPLETED" if job.stage == "READY" else "FAILED"
        response.waiting_reason = None
        response.retry_at = None
    elif job.stage == "INDEXING":
        response.work_state = "VERIFYING" if not response.waiting_reason else response.work_state


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
        metadata = await self.repository.active_metadata(organization_id, workspace_id)
        work_items = await self.repository.embedding_work_items(organization_id, workspace_id)
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
                response.embedded_chunks = getattr(job, "embedded_chunks", None)
                response.total_chunks = getattr(job, "total_chunks", None)
                attach_work_state(response, job, work_items.get(version.id))
                response.mime_type = getattr(version, "mime_type", None)
                response.size_bytes = getattr(version, "size_bytes", None)
                indexed = metadata.get(version.id)
                response.chunk_count = indexed.chunk_count if indexed else None
                response.indexed_at = indexed.indexed_at if indexed else None
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
        version = await self.repository.latest_version(organization_id, workspace_id, document_id)
        jobs = await self.repository.list_document_jobs(organization_id, workspace_id, document_id)
        metadata = await self.repository.active_metadata(organization_id, workspace_id, document_id)
        snapshot = await self.repository.embedding_snapshot(organization_id, workspace_id)
        item = DocumentResponse.model_validate(document, from_attributes=True)
        work_items = await self.repository.embedding_work_items(organization_id, workspace_id)
        if version:
            item.document_version_id = version.id
            item.mime_type, item.size_bytes = version.mime_type, version.size_bytes
            indexed = metadata.get(version.id)
            if indexed and snapshot:
                item.chunk_count, item.indexed_at = indexed.chunk_count, indexed.indexed_at
                item.embedding_model_id = snapshot.provider_config_id
                item.embedding_model_name, item.embedding_dimension = (
                    snapshot.model,
                    snapshot.dimension,
                )
        if document_id in jobs:
            latest, job = jobs[document_id]
            item.job_id, item.stage, item.progress = job.id, job.stage, job.progress
            item.attempts, item.error_code = job.attempts, job.error_code
            item.error_message = ingestion_error_message(job.error_code)
            attach_work_state(item, job, work_items.get(latest.id))
            item.retryable = latest.status == "FAILED" and job.error_code in RETRYABLE_ERROR_CODES
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
