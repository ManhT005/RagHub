import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ingestion_lock import ingestion_lock_key
from app.modules.documents.models import (
    Document,
    DocumentStatus,
    DocumentVersion,
    IngestionJob,
)
from app.modules.ingestion.errors import ingestion_error_message
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
                error_message=ingestion_error_message("QUEUE_UNAVAILABLE"),
            )
        )

    async def list_documents(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[Document]:
        rows = await self.session.scalars(
            select(Document)
            .where(
                Document.organization_id == organization_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
        )
        return list(rows)

    async def find_version_for_retry(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID, version_id: uuid.UUID
    ) -> tuple[Document, DocumentVersion, IngestionJob] | None:
        row = await self.session.execute(
            select(Document, DocumentVersion, IngestionJob)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .join(IngestionJob, IngestionJob.document_version_id == DocumentVersion.id)
            .join(Workspace, Workspace.id == Document.workspace_id)
            .where(
                DocumentVersion.id == version_id,
                Document.organization_id == organization_id,
                Document.workspace_id == workspace_id,
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.workspace_id == workspace_id,
                Workspace.organization_id == organization_id,
                Workspace.deleted_at.is_(None),
                Document.deleted_at.is_(None),
            )
            .with_for_update(of=(DocumentVersion, IngestionJob))
            .execution_options(populate_existing=True)
        )
        return row.one_or_none()

    async def try_retry_lock(self, version_id: uuid.UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(func.pg_try_advisory_xact_lock(ingestion_lock_key(version_id)))
            )
        )

    async def list_document_jobs(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> dict[uuid.UUID, tuple[DocumentVersion, IngestionJob]]:
        rows = await self.session.execute(
            select(DocumentVersion, IngestionJob)
            .join(IngestionJob, IngestionJob.document_version_id == DocumentVersion.id)
            .where(
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.workspace_id == workspace_id,
            )
            .order_by(DocumentVersion.created_at.desc())
        )
        jobs: dict[uuid.UUID, tuple[DocumentVersion, IngestionJob]] = {}
        for version, job in rows:
            jobs.setdefault(version.document_id, (version, job))
        return jobs

    async def find_document(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        return await self.session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.organization_id == organization_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
        )
