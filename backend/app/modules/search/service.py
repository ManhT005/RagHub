from uuid import UUID

from elasticsearch import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.infrastructure.elasticsearch.chunks import ChunkSearch
from app.modules.ai_providers.errors import ProviderError
from app.modules.ai_providers.resolver import ProviderResolver


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
            return await search.search(
                organization_id=organization_id,
                workspace_id=workspace_id,
                query=query,
                query_vector=query_vector,
                limit=limit,
            )
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
