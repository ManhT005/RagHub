from uuid import UUID

from elasticsearch import NotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.infrastructure.elasticsearch.chunks import ChunkSearch
from app.modules.ai_providers.errors import ProviderError
from app.modules.ai_providers.resolver import ProviderResolver
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.search.hybrid import RETRIEVAL_CANDIDATES


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _ready_hits(
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

    async def retrieve(
        self,
        organization_id: UUID,
        workspace_id: UUID,
        query: str,
        limit: int,
    ) -> list[dict[str, object]]:
        resolved = await ProviderResolver(self.session).embedding_for_workspace(
            organization_id, workspace_id
        )
        query_vector = await resolved.provider.embed_query(query)
        if len(query_vector) != resolved.index_version.dimension:
            raise AppError(
                "PROVIDER_INVALID_RESPONSE",
                "Query embedding dimension does not match the active index.",
                status_code=502,
            )
        search = ChunkSearch(index_name=resolved.index_version.index_name)
        try:
            candidates = await search.search(
                organization_id=organization_id,
                workspace_id=workspace_id,
                query=query,
                query_vector=query_vector,
                limit=max(limit, RETRIEVAL_CANDIDATES),
            )
            return (await self._ready_hits(organization_id, workspace_id, candidates))[:limit]
        except NotFoundError:
            return []
        except ProviderError:
            raise
        except Exception as exc:
            raise AppError(
                "SEARCH_UNAVAILABLE", "Search is temporarily unavailable.", status_code=503
            ) from exc
        finally:
            await search.close()
