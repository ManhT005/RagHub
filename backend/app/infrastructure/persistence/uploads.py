from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core_domain.documents.upload import UploadReceipt
from app.modules.documents.repository import DocumentRepository


class UploadRepositoryAdapter:
    def __init__(self, repository: DocumentRepository, session: AsyncSession) -> None:
        self.repository, self.session = repository, session

    async def workspace_exists(self, organization_id: UUID, workspace_id: UUID) -> bool:
        return await self.repository.workspace_exists(organization_id, workspace_id)

    async def create_upload(self, **kwargs) -> UploadReceipt:
        document, version, job = await self.repository.create_upload(**kwargs)
        return UploadReceipt(document.id, version.id, job.id, version.status, version.created_at)

    async def mark_queue_failure(self, version_id: UUID, message: str) -> None:
        await self.repository.mark_queue_failure(version_id, message)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
