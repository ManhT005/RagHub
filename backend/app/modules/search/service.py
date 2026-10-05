from uuid import UUID

from raghub_core.domain.retrieval.models import RetrievalScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.self_host import SelfHostContainer
from app.infrastructure.persistence.readiness import DocumentReadinessAdapter
from app.infrastructure.retrieval_mapping import chunk_to_hit


class SearchService:
    """Compatibility facade for HTTP search consumers."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.container = SelfHostContainer(session)

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
        results = await self.container.retrieve_context().retrieve(
            RetrievalScope(organization_id, workspace_id),
            query,
            limit,
        )
        return [chunk_to_hit(hit) for hit in results]
