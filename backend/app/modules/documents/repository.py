import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import (
    Document,
    DocumentStatus,
    DocumentVersion,
    IngestionJob,
)
from app.modules.workspaces.models import Workspace


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def workspace_exists(self, organization_id: uuid.UUID, workspace_id: uuid.UUID) -> bool:
        result = await self.session.scalar(
            select(Workspace.id).where(
                Workspace.id == workspace_id,
                Workspace.organization_id == organization_id,
                Workspace.deleted_at.is_(None),
            )
        )
        return result is not None

    async def create_upload(
        self,
        *,
        organization_id: uuid.UUID,
        workspace_id: uuid.UUID,
        filename: str,
        storage_key: str,
        checksum: str,
        mime_type: str,
        size_bytes: int,
    ) -> tuple[Document, DocumentVersion, IngestionJob]:
        document = Document(
            organization_id=organization_id,
            workspace_id=workspace_id,
            name=filename,
            status=DocumentStatus.QUEUED,
        )
        self.session.add(document)
        await self.session.flush()

        version = DocumentVersion(
            document_id=document.id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            storage_key=storage_key,
            checksum=checksum,
            mime_type=mime_type,
            size_bytes=size_bytes,
            status=DocumentStatus.QUEUED,
        )
        self.session.add(version)
        await self.session.flush()

        job = IngestionJob(
            document_version_id=version.id,
            stage=DocumentStatus.QUEUED,
            progress=0,
        )
        self.session.add(job)
        await self.session.flush()
        return document, version, job

    async def mark_queue_failure(self, version_id: uuid.UUID, message: str) -> None:
        document_id = await self.session.scalar(
            select(DocumentVersion.document_id).where(DocumentVersion.id == version_id)
        )
        await self.session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id == version_id)
            .values(status=DocumentStatus.FAILED)
        )
        if document_id is not None:
            await self.session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status=DocumentStatus.FAILED)
            )
        await self.session.execute(
            update(IngestionJob)
            .where(IngestionJob.document_version_id == version_id)
            .values(
                stage=DocumentStatus.FAILED,
                error_code="QUEUE_UNAVAILABLE",
                error_message=message[:2000],
            )
        )
