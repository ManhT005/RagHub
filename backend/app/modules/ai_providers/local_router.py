from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import OrganizationContext, get_organization_context, require_role
from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.ai_providers.local_manager import LocalModelManager
from app.modules.memberships.models import MembershipRole

router = APIRouter(prefix="/organizations/{organization_id}/local-ai", tags=["Local AI"])
Context = Annotated[OrganizationContext, Depends(get_organization_context)]
Session = Annotated[AsyncSession, Depends(get_session)]


def scope(context, organization_id):
    require_role(context, MembershipRole.ADMIN)
    if context.organization_id != organization_id:
        raise AppError(
            "ORGANIZATION_SCOPE_MISMATCH", "Organization scope mismatch.", status_code=400
        )


@router.get("/models")
async def models(organization_id: UUID, context: Context, session: Session):
    scope(context, organization_id)
    return await LocalModelManager(session).catalog(organization_id)


@router.post("/models/{catalog_id}/download", status_code=202)
async def download(organization_id: UUID, catalog_id: str, context: Context, session: Session):
    scope(context, organization_id)
    return await LocalModelManager(session).start(organization_id, catalog_id)
