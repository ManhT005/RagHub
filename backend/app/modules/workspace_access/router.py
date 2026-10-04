from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    OrganizationContext,
    get_organization_context,
    require_workspace_permission,
    workspace_permissions,
)
from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.memberships.models import (
    Membership,
    MembershipRole,
    WorkspaceMembership,
    WorkspaceMembershipPermission,
)
from app.modules.users.models import User
from app.modules.workspace_access.permissions import normalize_permissions

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["workspace access"])
Context = Annotated[OrganizationContext, Depends(get_organization_context)]
Session = Annotated[AsyncSession, Depends(get_session)]


class PermissionInput(BaseModel):
    permissions: list[str] = Field(default_factory=list, max_length=32)


class MemberInput(PermissionInput):
    user_id: UUID


class MemberResponse(PermissionInput):
    user_id: UUID
    email: str
    display_name: str | None = None
    status: str


class MyPermissions(BaseModel):
    workspace_id: UUID
    is_system_admin: bool
    permissions: list[str]


@router.get("/me/permissions", response_model=MyPermissions)
async def my_permissions(workspace_id: UUID, context: Context, session: Session):
    permissions = await workspace_permissions(context, workspace_id, session)
    return MyPermissions(
        workspace_id=workspace_id,
        is_system_admin=context.membership.role == MembershipRole.ADMIN,
        permissions=permissions,
    )


@router.get("/members/candidates", response_model=list[MemberResponse])
async def candidates(workspace_id: UUID, context: Context, session: Session):
    await require_workspace_permission(context, workspace_id, "member.manage", session)
    rows = await session.execute(
        select(User, Membership.status)
        .join(
            Membership,
            Membership.user_id == User.id,
        )
        .where(
            Membership.organization_id == context.organization_id,
            Membership.role == MembershipRole.WORKSPACE_ADMIN,
            Membership.status == "ACTIVE",
            User.status == "ACTIVE",
        )
        .order_by(User.email)
    )
    return [
        MemberResponse(
            user_id=user.id, email=user.email, display_name=user.display_name, status=member_status
        )
        for user, member_status in rows
    ]


@router.get("/members", response_model=list[MemberResponse])
async def members(workspace_id: UUID, context: Context, session: Session):
    await require_workspace_permission(context, workspace_id, "member.view", session)
    rows = await session.execute(
        select(User, Membership.status)
        .join(
            WorkspaceMembership,
            WorkspaceMembership.user_id == User.id,
        )
        .join(Membership, Membership.user_id == User.id)
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            Membership.organization_id == context.organization_id,
        )
        .order_by(User.email)
    )
    grants = await session.execute(
        select(WorkspaceMembershipPermission).where(
            WorkspaceMembershipPermission.workspace_id == workspace_id,
        )
    )
    by_user: dict[UUID, list[str]] = {}
    for grant in grants.scalars():
        by_user.setdefault(grant.user_id, []).append(grant.permission)
    return [
        MemberResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            status=member_status,
            permissions=sorted(by_user.get(user.id, [])),
        )
        for user, member_status in rows
    ]


async def save(
    workspace_id: UUID,
    user_id: UUID,
    payload: PermissionInput,
    context: OrganizationContext,
    session: AsyncSession,
    *,
    create: bool,
):
    await require_workspace_permission(context, workspace_id, "member.manage", session)
    # Serialize editors for one workspace, including simultaneous first assignments.
    from app.modules.workspaces.models import Workspace

    await session.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    membership = await session.get(Membership, (user_id, context.organization_id))
    user = await session.get(User, user_id)
    if membership is None or membership.status != "ACTIVE" or user is None:
        raise AppError(
            "MEMBERSHIP_NOT_FOUND", "Active organization member required.", status_code=404
        )
    if membership.role == MembershipRole.ADMIN:
        raise AppError(
            "SYSTEM_ADMIN_ASSIGNMENT", "System administrators already have access.", status_code=409
        )
    permissions = normalize_permissions(payload.permissions)
    assignment = await session.get(WorkspaceMembership, (user_id, workspace_id))
    if assignment is None:
        if not create:
            raise AppError("MEMBERSHIP_NOT_FOUND", "Workspace member not found.", status_code=404)
        session.add(WorkspaceMembership(user_id=user_id, workspace_id=workspace_id))
        await session.flush()
    await session.execute(
        delete(WorkspaceMembershipPermission).where(
            WorkspaceMembershipPermission.user_id == user_id,
            WorkspaceMembershipPermission.workspace_id == workspace_id,
        )
    )
    session.add_all(
        [
            WorkspaceMembershipPermission(
                user_id=user_id, workspace_id=workspace_id, permission=permission
            )
            for permission in permissions
        ]
    )
    await session.commit()
    return MemberResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=membership.status,
        permissions=permissions,
    )


@router.post("/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def assign(workspace_id: UUID, payload: MemberInput, context: Context, session: Session):
    return await save(workspace_id, payload.user_id, payload, context, session, create=True)


@router.patch("/members/{user_id}", response_model=MemberResponse)
async def update(
    workspace_id: UUID, user_id: UUID, payload: PermissionInput, context: Context, session: Session
):
    return await save(workspace_id, user_id, payload, context, session, create=False)


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(workspace_id: UUID, user_id: UUID, context: Context, session: Session):
    await require_workspace_permission(context, workspace_id, "member.manage", session)
    assignment = await session.get(WorkspaceMembership, (user_id, workspace_id))
    if assignment is None:
        raise AppError("MEMBERSHIP_NOT_FOUND", "Workspace member not found.", status_code=404)
    await session.delete(assignment)
    await session.commit()
