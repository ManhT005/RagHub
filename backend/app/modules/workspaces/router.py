from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import OrganizationContext, get_organization_context, require_role
from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.memberships.models import MembershipRole
from app.modules.workspaces.models import Workspace

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class WorkspaceInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,99}$")


class WorkspaceResponse(WorkspaceInput):
    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime | None = None


def response(workspace: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse.model_validate(workspace, from_attributes=True)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[WorkspaceResponse]:
    rows = await session.scalars(
        select(Workspace)
        .where(Workspace.organization_id == context.organization_id, Workspace.deleted_at.is_(None))
        .order_by(Workspace.name)
    )
    return [response(workspace) for workspace in rows]


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceInput,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkspaceResponse:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    exists = await session.scalar(
        select(Workspace.id).where(
            Workspace.organization_id == context.organization_id, Workspace.slug == payload.slug
        )
    )
    if exists:
        raise AppError(
            "WORKSPACE_SLUG_TAKEN", "This workspace slug is already in use.", status_code=409
        )
    workspace = Workspace(
        organization_id=context.organization_id, name=payload.name.strip(), slug=payload.slug
    )
    session.add(workspace)
    await session.commit()
    await session.refresh(workspace)
    return response(workspace)


async def get_workspace(
    workspace_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Workspace:
    workspace = await session.scalar(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.organization_id == context.organization_id,
            Workspace.deleted_at.is_(None),
        )
    )
    if workspace is None:
        raise AppError(
            "WORKSPACE_NOT_FOUND",
            "Workspace was not found in the current organization.",
            status_code=404,
        )
    return workspace


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def read_workspace(
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> WorkspaceResponse:
    return response(workspace)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    payload: WorkspaceInput,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkspaceResponse:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    workspace.name, workspace.slug = payload.name.strip(), payload.slug
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise AppError(
            "WORKSPACE_SLUG_TAKEN", "This workspace slug is already in use.", status_code=409
        ) from exc
    await session.refresh(workspace)
    return response(workspace)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace: Annotated[Workspace, Depends(get_workspace)],
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN)
    workspace.deleted_at = datetime.now().astimezone()
    await session.commit()
