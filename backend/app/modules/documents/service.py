import hashlib
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import anyio
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.infrastructure.elasticsearch.chunks import ChunkIndexer
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.modules.documents.repository import DocumentRepository
from app.modules.documents.schemas import DocumentAccepted, DocumentResponse
from app.modules.ingestion.errors import RETRYABLE_ERROR_CODES, ingestion_error_message

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {
    ".pdf": {"application/pdf", "application/x-pdf"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
}


class DocumentService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = DocumentRepository(session)
        self.storage = MinioObjectStorage(self.settings)

    async def upload_document(
        self,
        *,
        organization_id: uuid.UUID,
        workspace_id: uuid.UUID,
        upload: UploadFile,
    ) -> DocumentAccepted:
        if not await self.repository.workspace_exists(organization_id, workspace_id):
            raise AppError(
                "WORKSPACE_NOT_FOUND",
                "Workspace was not found in the current organization.",
                status_code=404,
            )

        filename = Path((upload.filename or "").replace("\\", "/")).name
        extension = Path(filename).suffix.lower()
        if not filename or extension not in SUPPORTED_TYPES:
            raise AppError(
                "UNSUPPORTED_FILE_TYPE", "Only PDF, TXT and Markdown files are supported."
            )
        mime_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
        if mime_type not in SUPPORTED_TYPES[extension]:
            raise AppError(
                "INVALID_CONTENT_TYPE",
                "The content type does not match the file extension.",
            )

        content = await self._read_limited(upload)
        if extension == ".pdf" and not content.startswith(b"%PDF-"):
            raise AppError("INVALID_PDF", "The uploaded file is not a valid PDF.")

        checksum = hashlib.sha256(content).hexdigest()
        storage_key = f"{organization_id}/{workspace_id}/{uuid.uuid4()}{extension}"
        try:
            await anyio.to_thread.run_sync(
                lambda: self.storage.put(storage_key, content, mime_type)
            )
        except Exception as exc:
            raise AppError(
                "STORAGE_UNAVAILABLE",
                "The document could not be stored.",
                status_code=503,
            ) from exc

        try:
            document, version, job = await self.repository.create_upload(
                organization_id=organization_id,
                workspace_id=workspace_id,
                filename=filename,
                storage_key=storage_key,
                checksum=checksum,
                mime_type=mime_type,
                size_bytes=len(content),
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            try:
                await anyio.to_thread.run_sync(lambda: self.storage.remove(storage_key))
            except Exception:
                pass
            raise

        try:
            from app.workers.tasks import ingest_document_version

            ingest_document_version.delay(str(version.id))
        except Exception as exc:
            logger.exception("Could not enqueue document version %s", version.id)
            await self.repository.mark_queue_failure(version.id, str(exc))
            await self.session.commit()
            raise AppError(
                "QUEUE_UNAVAILABLE",
                "The document was stored but could not be queued for ingestion.",
                status_code=503,
                details={"document_id": str(document.id)},
            ) from exc

        return DocumentAccepted(
            document_id=document.id,
            document_version_id=version.id,
            job_id=job.id,
            status=version.status,
            created_at=version.created_at,
        )

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
            from app.workers.tasks import ingest_document_version

            ingest_document_version.delay(str(version.id))
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
        try:
            def remove_existing_chunks() -> None:
                indexer = ChunkIndexer(self.settings)
                try:
                    indexer.delete_document_version(version.id)
                finally:
                    indexer.close()

            await anyio.to_thread.run_sync(remove_existing_chunks)
        except Exception as exc:
            raise AppError(
                "INDEX_UNAVAILABLE",
                "The existing search index could not be cleared.",
                status_code=503,
            ) from exc
        document.status = version.status = job.stage = "QUEUED"
        job.progress = job.attempts = 0
        job.error_code = job.error_message = job.error_details = None
        await self.session.commit()
        try:
            from app.workers.tasks import ingest_document_version

            ingest_document_version.delay(str(version.id))
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

    async def _read_limited(self, upload: UploadFile) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > self.settings.max_upload_size_bytes:
                raise AppError(
                    "FILE_TOO_LARGE",
                    f"The upload exceeds {self.settings.max_upload_size_mb} MB.",
                    status_code=413,
                )
            chunks.append(chunk)
        if total == 0:
            raise AppError("EMPTY_FILE", "The uploaded file is empty.")
        return b"".join(chunks)
