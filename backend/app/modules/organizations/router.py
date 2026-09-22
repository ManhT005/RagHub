from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    OrganizationContext,
    get_current_user,
    get_organization_context,
    require_role,
)
from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.memberships.models import Membership, MembershipRole
from app.modules.organizations.models import Organization
from app.modules.users.models import User

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,99}$")


class OrganizationResponse(OrganizationInput):
    id: UUID
    role: str


class MembershipInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: MembershipRole = MembershipRole.EDITOR


class MembershipResponse(BaseModel):
    user_id: UUID
    email: str
    role: MembershipRole


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
        Membership(user_id=user.id, organization_id=organization.id, role=MembershipRole.OWNER)
    )
    await session.commit()
    return organization_response(organization, MembershipRole.OWNER)


@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[OrganizationResponse]:
    rows = await session.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user.id, Organization.status == "ACTIVE")
        .order_by(Organization.name)
    )
    return [organization_response(organization, role) for organization, role in rows]


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
    rows = await session.execute(
        select(Membership, User.email)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == organization_id)
        .order_by(User.email)
    )
    return [
        MembershipResponse(user_id=membership.user_id, email=email, role=membership.role)
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
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN)
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None:
        raise AppError(
            "USER_NOT_FOUND", "Invitee must register before being added.", status_code=404
        )
    membership = await session.get(Membership, (user.id, organization_id))
    if membership is None:
        membership = Membership(user_id=user.id, organization_id=organization_id, role=payload.role)
        session.add(membership)
    else:
        membership.role = payload.role
    await session.commit()
    return MembershipResponse(user_id=user.id, email=user.email, role=membership.role)


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
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN)
    membership = await session.get(Membership, (user_id, organization_id))
    if membership is None:
        raise AppError("MEMBERSHIP_NOT_FOUND", "Member was not found.", status_code=404)
    if membership.role == MembershipRole.OWNER:
        raise AppError(
            "OWNER_MEMBERSHIP_PROTECTED",
            "The organization owner cannot be removed.",
            status_code=409,
        )
    session.delete(membership)
    await session.commit()
