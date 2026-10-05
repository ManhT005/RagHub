from uuid import UUID

from raghub_core.domain.retrieval.models import RetrievalScope, RetrievedChunk
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.retrieval_mapping import chunk_to_hit
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion


class DocumentReadinessAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ready_hits(
        self,
        organization_id: UUID,
        workspace_id: UUID,
        hits: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Keep only hits whose document and exact version are currently usable."""
        document_ids = {UUID(str(hit["document_id"])) for hit in hits}
        version_ids = {UUID(str(hit["document_version_id"])) for hit in hits}
        if not document_ids or not version_ids:
            return []

        rows = await self.session.execute(
            select(Document.id, DocumentVersion.id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(
                Document.id.in_(document_ids),
                DocumentVersion.id.in_(version_ids),
                Document.organization_id == organization_id,
                Document.workspace_id == workspace_id,
                Document.status == DocumentStatus.READY,
                Document.deleted_at.is_(None),
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.workspace_id == workspace_id,
                DocumentVersion.status == DocumentStatus.READY,
            )
        )
        ready_pairs = {(str(document_id), str(version_id)) for document_id, version_id in rows}
        return [
            hit
            for hit in hits
            if (str(hit["document_id"]), str(hit["document_version_id"])) in ready_pairs
        ]

    async def filter_ready(
        self, scope: RetrievalScope, hits: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        ready = await self.ready_hits(
            scope.organization_id, scope.workspace_id, [chunk_to_hit(hit) for hit in hits]
        )
        pairs = {(hit["document_id"], hit["document_version_id"]) for hit in ready}
        return [
            hit for hit in hits if (str(hit.document_id), str(hit.document_version_id)) in pairs
        ]
