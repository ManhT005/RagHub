from uuid import UUID

from raghub_core.domain.documents.upload import RetryDocumentState, UploadReceipt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_providers.models import EmbeddingIndexVersion, EmbeddingWorkItem
from app.modules.documents.repository import DocumentRepository
from app.modules.workspaces.models import Workspace


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


class DocumentRetryRepositoryAdapter(UploadRepositoryAdapter):
    async def load_for_retry(self, scope, version_id) -> RetryDocumentState | None:
        self.scope = scope
        self.rows = await self.repository.find_version_for_retry(
            scope.organization_id,
            scope.workspace_id,
            version_id,
        )
        if self.rows is None:
            return None
        document, version, job = self.rows
        # Validation can reject an invalid state before needing the receipt's other fields.
        return RetryDocumentState(
            UploadReceipt(
                document.id,
                version.id,
                job.id,
                version.status,
                version.created_at,
            ),
            job.error_code,
        )

    async def try_retry_lock(self, version_id) -> bool:
        return await self.repository.try_retry_lock(version_id)

    async def reset(self, version_id) -> UploadReceipt:
        document, version, job = self.rows
        document.status = version.status = job.stage = "QUEUED"
        job.progress = job.attempts = 0
        job.error_code = job.error_message = job.error_details = None
        active_index = (
            select(EmbeddingIndexVersion.index_name)
            .join(
                Workspace, Workspace.active_embedding_index_version_id == EmbeddingIndexVersion.id
            )
            .where(
                Workspace.id == self.scope.workspace_id,
                Workspace.organization_id == self.scope.organization_id,
            )
            .scalar_subquery()
        )
        await self.session.execute(
            update(EmbeddingWorkItem)
            .where(
                EmbeddingWorkItem.document_version_id == version_id,
                EmbeddingWorkItem.organization_id == self.scope.organization_id,
                EmbeddingWorkItem.workspace_id == self.scope.workspace_id,
                EmbeddingWorkItem.index_name == active_index,
                EmbeddingWorkItem.state == "FAILED",
            )
            .values(
                state="QUEUED",
                kind="recovery",
                available_at=None,
                error_code=None,
                error_message=None,
            )
        )
        return UploadReceipt(document.id, version.id, job.id, version.status, version.created_at)
