from typing import Protocol
from uuid import UUID

from app.core_domain.documents.upload import UploadReceipt


class DocumentRepositoryPort(Protocol):
    async def workspace_exists(self, organization_id: UUID, workspace_id: UUID) -> bool: ...
    async def create_upload(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        filename: str,
        storage_key: str,
        checksum: str,
        mime_type: str,
        size_bytes: int,
    ) -> UploadReceipt: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
    async def mark_queue_failure(self, version_id: UUID, message: str) -> None: ...
