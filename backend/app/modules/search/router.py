from typing import Annotated
from uuid import UUID

from elasticsearch import NotFoundError
from fastapi import APIRouter, Depends, Query

from app.core.auth import OrganizationContext, get_organization_context
from app.core.exceptions import AppError
from app.infrastructure.elasticsearch.chunks import ChunkSearch
from app.modules.search.hybrid import build_context
from app.modules.search.schemas import SearchResponse

router = APIRouter(prefix="/workspaces", tags=["search"])


@router.get("/{workspace_id}/search", response_model=SearchResponse)
async def search_workspace(
    workspace_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=5)] = 5,
) -> SearchResponse:
    search = ChunkSearch()
    try:
        hits = await search.search(
            organization_id=context.organization_id,
            workspace_id=workspace_id,
            query=q,
            limit=limit,
        )
    except NotFoundError:
        hits = []
    except Exception as exc:
        raise AppError(
            "SEARCH_UNAVAILABLE",
            "Search is temporarily unavailable.",
            status_code=503,
        ) from exc
    finally:
        await search.close()
    return SearchResponse(query=q, hits=hits, context=build_context(hits))
