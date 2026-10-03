import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_providers.models import EmbeddingIndexVersion, EmbeddingReindexJob
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.workspaces.models import Workspace
from raghub_core.domain.ingestion.models import IngestionDocument
from raghub_core.domain.ingestion.reindex import ReindexTarget
from raghub_core.domain.providers.enums import IndexVersionStatus, ReindexJobStatus
from raghub_core.domain.retrieval.models import RetrievalScope

logger = logging.getLogger(__name__)


class ReindexRepositoryAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.job: EmbeddingReindexJob | None = None

    async def load(self, job_id: UUID) -> ReindexTarget | None:
        self.job = await self.session.get(EmbeddingReindexJob, job_id)
        if self.job is None:
            return None
        version = await self.session.get(EmbeddingIndexVersion, self.job.target_index_version_id)
        workspace = await self.session.get(Workspace, self.job.workspace_id)
        if version is None or workspace is None:
            return None
        return ReindexTarget(
            job_id,
            RetrievalScope(self.job.organization_id, self.job.workspace_id),
            version.id,
            self.job.status,
            workspace.pending_embedding_index_version_id == version.id,
        )

    async def mark(self, job_id: UUID, status: str) -> None:
        self.job.status = status
        if status == ReindexJobStatus.RUNNING:
            self.job.started_at = self.job.started_at or datetime.now(UTC)
        if status == ReindexJobStatus.SUPERSEDED:
            self.job.completed_at = datetime.now(UTC)
        await self.session.commit()

    async def latest_documents(self, target: ReindexTarget) -> list[IngestionDocument]:
        rows = (
            await self.session.execute(
                select(Document, DocumentVersion)
                .join(DocumentVersion, DocumentVersion.document_id == Document.id)
                .where(
                    Document.organization_id == target.scope.organization_id,
                    Document.workspace_id == target.scope.workspace_id,
                    Document.status == DocumentStatus.READY,
                    Document.deleted_at.is_(None),
                    DocumentVersion.organization_id == target.scope.organization_id,
                    DocumentVersion.workspace_id == target.scope.workspace_id,
                    DocumentVersion.status == DocumentStatus.READY,
                )
                .order_by(DocumentVersion.created_at.desc())
            )
        ).all()
        seen: set[UUID] = set()
        documents = []
        for document, version in rows:
            if document.id not in seen:
                documents.append(
                    IngestionDocument(
                        target.scope,
                        document.id,
                        version.id,
                        version.storage_key,
                        document.name,
                    )
                )
                seen.add(document.id)
        return documents

    async def reset_progress(self, job_id: UUID, total: int) -> None:
        self.job.total_documents = total
        self.job.processed_documents = self.job.failed_documents = 0
        await self.session.commit()

    async def processed(self, job_id: UUID) -> None:
        self.job.processed_documents += 1
        await self.session.commit()

    async def activate(self, target: ReindexTarget) -> bool:
        # Serialize activation with workspace binding changes and refresh after the lock.
        workspace = await self.session.scalar(
            select(Workspace)
            .where(
                Workspace.id == target.scope.workspace_id,
                Workspace.organization_id == target.scope.organization_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        version = await self.session.get(EmbeddingIndexVersion, target.index_version_id)
        if workspace is None or workspace.pending_embedding_index_version_id != version.id:
            self.job.status = ReindexJobStatus.SUPERSEDED
            self.job.completed_at = datetime.now(UTC)
            version.status = IndexVersionStatus.FAILED
            await self.session.commit()
            return False
        old = (
            await self.session.get(
                EmbeddingIndexVersion, workspace.active_embedding_index_version_id
            )
            if workspace.active_embedding_index_version_id
            else None
        )
        if old and old.id != version.id:
            old.status = IndexVersionStatus.RETIRED
        version.status = IndexVersionStatus.ACTIVE
        version.activated_at = datetime.now(UTC)
        workspace.active_embedding_index_version_id = version.id
        workspace.embedding_provider_id = version.provider_config_id
        workspace.pending_embedding_index_version_id = None
        self.job.status = ReindexJobStatus.COMPLETED
        self.job.completed_at = datetime.now(UTC)
        await self.session.commit()
        return True

    async def rollback(self) -> None:
        await self.session.rollback()

    async def fail(self, job_id: UUID, exc: Exception) -> None:
        await self.session.rollback()
        job = await self.session.get(EmbeddingReindexJob, job_id)
        if job is None:
            return
        version = await self.session.get(EmbeddingIndexVersion, job.target_index_version_id)
        job.status = ReindexJobStatus.FAILED
        job.failed_documents = max(
            job.failed_documents, max(1, job.total_documents - job.processed_documents)
        )
        job.error_code = "EMBEDDING_REINDEX_FAILED"
        job.error_message = "The embedding index could not be rebuilt."
        job.completed_at = datetime.now(UTC)
        if version:
            version.status = IndexVersionStatus.FAILED
        await self.session.commit()
        logger.exception("Embedding re-index job %s failed", job_id, exc_info=exc)
