from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    OrganizationContext,
    get_current_user,
    get_organization_context,
    require_role,
)
from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.memberships.models import Membership, MembershipRole, WorkspaceMembership
from app.modules.organizations.models import Organization
from app.modules.users.models import User
from app.modules.workspaces.models import Workspace

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,99}$")


class OrganizationResponse(OrganizationInput):
    id: UUID
    role: MembershipRole


class MembershipInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: MembershipRole = MembershipRole.WORKSPACE_ADMIN
    workspace_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_workspace_scope(self):
        if self.role == MembershipRole.WORKSPACE_ADMIN and not self.workspace_ids:
            raise ValueError("workspace_ids is required for WORKSPACE_ADMIN")
        if self.role == MembershipRole.ADMIN and self.workspace_ids:
            raise ValueError("ADMIN cannot be limited to workspace_ids")
        return self


class MembershipResponse(BaseModel):
    user_id: UUID
    email: str
    role: MembershipRole
    status: str = "ACTIVE"
    workspace_ids: list[UUID] = Field(default_factory=list)


def organization_response(organization: Organization, role: str) -> OrganizationResponse:
    return OrganizationResponse(
        id=organization.id, name=organization.name, slug=organization.slug, role=role
    )


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationInput,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrganizationResponse:
    if await session.scalar(select(Organization.id).where(Organization.slug == payload.slug)):
        raise AppError(
            "ORGANIZATION_SLUG_TAKEN", "This organization slug is already in use.", status_code=409
        )
    organization = Organization(name=payload.name.strip(), slug=payload.slug)
    session.add(organization)
    await session.flush()
    session.add(
        Membership(user_id=user.id, organization_id=organization.id, role=MembershipRole.ADMIN)
    )
    await session.commit()
    return organization_response(organization, MembershipRole.ADMIN)


@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[OrganizationResponse]:
    rows = await session.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(
            Membership.user_id == user.id,
            Membership.status == "ACTIVE",
            Organization.status == "ACTIVE",
        )
        .order_by(Organization.name)
    )
    return [organization_response(organization, role) for organization, role in rows]


async def _workspace_ids(session: AsyncSession, user_id: UUID, organization_id: UUID) -> list[UUID]:
    rows = await session.scalars(
        select(WorkspaceMembership.workspace_id)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .where(
            WorkspaceMembership.user_id == user_id,
            Workspace.organization_id == organization_id,
        )
    )
    return list(rows)


@router.get("/{organization_id}/members", response_model=list[MembershipResponse])
async def list_members(
    organization_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[MembershipResponse]:
    if context.organization_id != organization_id:
        raise AppError(
            "ORGANIZATION_SCOPE_MISMATCH",
            "Organization scope does not match the path.",
            status_code=400,
        )
    require_role(context, MembershipRole.ADMIN)
    rows = await session.execute(
        select(Membership, User.email)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == organization_id)
        .order_by(User.email)
    )
    return [
        MembershipResponse(
            user_id=membership.user_id,
            email=email,
            role=membership.role,
            status=membership.status,
            workspace_ids=await _workspace_ids(session, membership.user_id, organization_id),
        )
        for membership, email in rows
    ]


@router.put("/{organization_id}/members", response_model=MembershipResponse)
async def upsert_member(
    organization_id: UUID,
    payload: MembershipInput,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MembershipResponse:
    if context.organization_id != organization_id:
        raise AppError(
            "ORGANIZATION_SCOPE_MISMATCH",
            "Organization scope does not match the path.",
            status_code=400,
        )
    require_role(context, MembershipRole.ADMIN)
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None:
        raise AppError(
            "USER_NOT_FOUND", "Invitee must register before being added.", status_code=404
        )
    if payload.workspace_ids:
        count = await session.scalar(
            select(sa.func.count())
            .select_from(Workspace)
            .where(
                Workspace.id.in_(payload.workspace_ids),
                Workspace.organization_id == organization_id,
                Workspace.deleted_at.is_(None),
            )
        )
        if count != len(set(payload.workspace_ids)):
            raise AppError(
                "INVALID_WORKSPACE_SCOPE", "One or more workspaces are invalid.", status_code=400
            )
    membership = await session.get(Membership, (user.id, organization_id))
    if membership is None:
        membership = Membership(user_id=user.id, organization_id=organization_id, role=payload.role)
        session.add(membership)
    else:
        membership.role = payload.role
    await session.execute(
        delete(WorkspaceMembership).where(
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.workspace_id.in_(
                select(Workspace.id).where(Workspace.organization_id == organization_id)
            ),
        )
    )
    for workspace_id in set(payload.workspace_ids):
        session.add(WorkspaceMembership(user_id=user.id, workspace_id=workspace_id))
    await session.commit()
    return MembershipResponse(
        user_id=user.id,
        email=user.email,
        role=membership.role,
        status=membership.status or "ACTIVE",
        workspace_ids=payload.workspace_ids,
    )


@router.delete("/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(
    organization_id: UUID,
    user_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    if context.organization_id != organization_id:
        raise AppError(
            "ORGANIZATION_SCOPE_MISMATCH",
            "Organization scope does not match the path.",
            status_code=400,
        )
    require_role(context, MembershipRole.ADMIN)
    membership = await session.get(Membership, (user_id, organization_id))
    if membership is None:
        raise AppError("MEMBERSHIP_NOT_FOUND", "Member was not found.", status_code=404)
    await session.delete(membership)
    await session.commit()
