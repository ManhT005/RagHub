from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import OrganizationContext, get_organization_context
from app.core.database import get_session
from app.modules.search.hybrid import build_context
from app.modules.search.schemas import SearchResponse
from app.modules.search.service import SearchService

router = APIRouter(prefix="/workspaces", tags=["search"])


@router.get("/{workspace_id}/search", response_model=SearchResponse)
async def search_workspace(
    workspace_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=5)] = 5,
) -> SearchResponse:
    hits = await SearchService(session).retrieve(context.organization_id, workspace_id, q, limit)
    return SearchResponse(query=q, hits=hits, context=build_context(hits))
