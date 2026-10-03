from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.retrieval import retrieval_use_case
from app.core_domain.retrieval.models import RetrievalScope
from app.infrastructure.persistence.readiness import DocumentReadinessAdapter


class SearchService:
    """Compatibility facade for HTTP search consumers."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _ready_hits(
        self, organization_id: UUID, workspace_id: UUID, hits: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        return await DocumentReadinessAdapter(self.session).ready_hits(
            organization_id,
            workspace_id,
            hits,
        )

    async def retrieve(
        self, organization_id: UUID, workspace_id: UUID, query: str, limit: int
    ) -> list[dict[str, object]]:
        results = await retrieval_use_case(self.session).retrieve(
            RetrievalScope(organization_id, workspace_id),
            query,
            limit,
        )
        return [hit.as_hit() for hit in results]
