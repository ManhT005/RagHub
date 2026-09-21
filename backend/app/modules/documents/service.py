import hashlib
import uuid
from pathlib import Path

import anyio
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.modules.documents.repository import DocumentRepository
from app.modules.documents.schemas import DocumentAccepted

PDF_MIME_TYPES = {"application/pdf", "application/x-pdf"}


class DocumentService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = DocumentRepository(session)
        self.storage = MinioObjectStorage(self.settings)

    async def upload_pdf(
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

        filename = Path(upload.filename or "").name
        if not filename or Path(filename).suffix.lower() != ".pdf":
            raise AppError("UNSUPPORTED_FILE_TYPE", "Only PDF files are supported.")
        if upload.content_type not in PDF_MIME_TYPES:
            raise AppError(
                "INVALID_CONTENT_TYPE",
                "The upload must use the application/pdf content type.",
            )

        content = await self._read_limited(upload)
        if not content.startswith(b"%PDF-"):
            raise AppError("INVALID_PDF", "The uploaded file is not a valid PDF.")

        checksum = hashlib.sha256(content).hexdigest()
        storage_key = f"{organization_id}/{workspace_id}/{uuid.uuid4()}.pdf"
        try:
            await anyio.to_thread.run_sync(
                lambda: self.storage.put(
                    storage_key, content, upload.content_type or "application/pdf"
                )
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
                mime_type=upload.content_type or "application/pdf",
                size_bytes=len(content),
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            await anyio.to_thread.run_sync(lambda: self.storage.remove(storage_key))
            raise

        try:
            from app.workers.tasks import ingest_document_version

            ingest_document_version.delay(str(version.id))
        except Exception as exc:
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
