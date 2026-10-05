import hashlib
from uuid import uuid4

from raghub_core.domain.documents.upload import (
    UploadDocumentCommand,
    UploadReceipt,
    validate_upload_content,
    validate_upload_metadata,
)
from raghub_core.domain.errors import CoreError
from raghub_core.ports.documents import DocumentRepositoryPort
from raghub_core.ports.object_storage import ObjectStoragePort
from raghub_core.ports.task_queue import TaskQueuePort


class UploadDocumentUseCase:
    def __init__(
        self,
        repository: DocumentRepositoryPort,
        storage: ObjectStoragePort,
        queue: TaskQueuePort,
        *,
        max_size_mb: int = 25,
    ) -> None:
        self.repository, self.storage, self.queue = repository, storage, queue
        self.max_size_mb = max_size_mb

    async def execute(self, command: UploadDocumentCommand) -> UploadReceipt:
        if not await self.repository.workspace_exists(
            command.organization_id, command.workspace_id
        ):
            raise CoreError(
                "WORKSPACE_NOT_FOUND",
                "Workspace was not found in the current organization.",
            )
        filename, extension, mime = validate_upload_metadata(command.filename, command.content_type)
        validate_upload_content(command.content, extension, self.max_size_mb)
        storage_key = f"{command.organization_id}/{command.workspace_id}/{uuid4()}{extension}"
        try:
            await self.storage.put(storage_key, command.content, mime)
        except Exception as exc:
            raise CoreError("STORAGE_UNAVAILABLE", "The document could not be stored.") from exc
        try:
            receipt = await self.repository.create_upload(
                organization_id=command.organization_id,
                workspace_id=command.workspace_id,
                filename=filename,
                storage_key=storage_key,
                checksum=hashlib.sha256(command.content).hexdigest(),
                mime_type=mime,
                size_bytes=len(command.content),
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            try:
                await self.storage.remove(storage_key)
            except Exception:
                pass
            raise
        try:
            self.queue.enqueue_ingestion(receipt.document_version_id)
        except Exception as exc:
            await self.repository.mark_queue_failure(receipt.document_version_id, str(exc))
            await self.repository.commit()
            raise CoreError(
                "QUEUE_UNAVAILABLE",
                "The document was stored but could not be queued for ingestion.",
                details={"document_id": str(receipt.document_id)},
            ) from exc
        return receipt
