"""Authentication and organization/workspace authorization dependencies."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.exceptions import AppError
from app.core.security import decode_token
from app.modules.memberships.models import (
    Membership,
    MembershipRole,
    WorkspaceMembership,
    WorkspaceMembershipPermission,
)
from app.modules.users.models import User
from app.modules.workspaces.models import Workspace

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None:
        raise AppError("AUTHENTICATION_REQUIRED", "A bearer token is required.", status_code=401)
    try:
        claims = decode_token(credentials.credentials, get_settings())
    except ValueError as exc:
        raise AppError(
            "INVALID_TOKEN", "The access token is invalid or expired.", status_code=401
        ) from exc
    user = await session.get(User, claims.user_id)
    if user is None or user.status != "ACTIVE" or user.auth_version != claims.auth_version:
        raise AppError(
            "AUTHENTICATION_REQUIRED", "The user account is unavailable.", status_code=401
        )
    return user


@dataclass(frozen=True)
class OrganizationContext:
    organization_id: UUID
    membership: Membership


async def get_organization_context(
    header_organization_id: Annotated[UUID, Header(alias="X-Organization-ID")],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrganizationContext:
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == header_organization_id, Membership.user_id == user.id
        )
    )
    if membership is None or getattr(membership, "status", "ACTIVE") != "ACTIVE":
        raise AppError(
            "ORGANIZATION_ACCESS_DENIED", "You do not belong to this organization.", status_code=403
        )
    return OrganizationContext(organization_id=header_organization_id, membership=membership)


def require_role(context: OrganizationContext, *roles: MembershipRole) -> None:
    if (
        getattr(context.membership, "status", "ACTIVE") != "ACTIVE"
        or context.membership.role not in roles
    ):
        raise AppError(
            "INSUFFICIENT_PERMISSION",
            "Your organization role cannot perform this action.",
            status_code=403,
        )


async def require_workspace_access(
    context: OrganizationContext, workspace_id: UUID, session: AsyncSession
) -> None:
    if context.membership.role == MembershipRole.ADMIN:
        return
    if context.membership.role != MembershipRole.WORKSPACE_ADMIN:
        raise AppError(
            "INSUFFICIENT_PERMISSION", "Your role cannot access workspaces.", status_code=403
        )
    assignment = await session.scalar(
        select(WorkspaceMembership)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .where(
            WorkspaceMembership.user_id == context.membership.user_id,
            WorkspaceMembership.workspace_id == workspace_id,
            Workspace.organization_id == context.organization_id,
            Workspace.deleted_at.is_(None),
        )
    )
    if assignment is None:
        raise AppError(
            "WORKSPACE_ACCESS_DENIED",
            "You are not assigned to this workspace.",
            status_code=403,
        )


async def workspace_permissions(
    context: OrganizationContext, workspace_id: UUID, session: AsyncSession
) -> list[str]:
    from app.modules.workspace_access.permissions import PERMISSIONS

    require_role(context, MembershipRole.ADMIN, MembershipRole.WORKSPACE_ADMIN)
    workspace = await session.scalar(
        select(Workspace.id).where(
            Workspace.id == workspace_id,
            Workspace.organization_id == context.organization_id,
            Workspace.deleted_at.is_(None),
        )
    )
    if workspace is None:
        raise AppError("WORKSPACE_ACCESS_DENIED", "Workspace is unavailable.", status_code=403)
    if context.membership.role == MembershipRole.ADMIN:
        return list(PERMISSIONS)
    await require_workspace_access(context, workspace_id, session)
    rows = await session.scalars(
        select(WorkspaceMembershipPermission.permission).where(
            WorkspaceMembershipPermission.workspace_id == workspace_id,
            WorkspaceMembershipPermission.user_id == context.membership.user_id,
        )
    )
    return sorted(set(rows) & set(PERMISSIONS))


async def require_workspace_permission(
    context: OrganizationContext, workspace_id: UUID, permission: str, session: AsyncSession
) -> None:
    if permission not in await workspace_permissions(context, workspace_id, session):
        raise AppError(
            "WORKSPACE_PERMISSION_DENIED", "Workspace permission is required.", status_code=403
        )
