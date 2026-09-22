"""Authentication and organization authorization dependencies."""

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
from app.modules.memberships.models import Membership, MembershipRole
from app.modules.users.models import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None:
        raise AppError("AUTHENTICATION_REQUIRED", "A bearer token is required.", status_code=401)
    try:
        user_id = decode_token(credentials.credentials, get_settings())
    except ValueError as exc:
        raise AppError(
            "INVALID_TOKEN", "The access token is invalid or expired.", status_code=401
        ) from exc
    user = await session.get(User, user_id)
    if user is None or user.status != "ACTIVE":
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
    if membership is None:
        raise AppError(
            "ORGANIZATION_ACCESS_DENIED", "You do not belong to this organization.", status_code=403
        )
    return OrganizationContext(organization_id=header_organization_id, membership=membership)


def require_role(context: OrganizationContext, *roles: MembershipRole) -> None:
    if context.membership.role not in roles:
        raise AppError(
            "INSUFFICIENT_PERMISSION",
            "Your organization role cannot perform this action.",
            status_code=403,
        )
