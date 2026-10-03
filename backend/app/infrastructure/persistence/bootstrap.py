"""Atomic installation bootstrap; unrelated identities are never adopted."""

from datetime import UTC, datetime

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, text

from app.core.security import hash_password
from app.modules.auth.models import IdentityProvider, UserIdentity
from app.modules.memberships.models import Membership, MembershipRole
from app.modules.organizations.models import Organization
from app.modules.users.models import User


class BootstrapOwnerInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128, repr=False)
    organization_slug: str = Field(default="raghub", pattern=r"^[a-z0-9-]{1,100}$")
    organization_name: str = Field(default="RagHub", min_length=1, max_length=200)


async def bootstrap_owner(session, payload: BootstrapOwnerInput) -> dict[str, str]:
    email = str(payload.email).lower()
    async with session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(7291042027)"))
        organization = await session.scalar(
            select(Organization).where(Organization.slug == payload.organization_slug)
        )
        if organization is None:
            organization = Organization(
                slug=payload.organization_slug,
                name=payload.organization_name,
                status="ACTIVE",
            )
            session.add(organization)
            await session.flush()
        if organization.status != "ACTIVE":
            raise ValueError("The installation organization is not active.")
        user = await session.scalar(select(User).where(func.lower(User.email) == email))
        if user is not None:
            membership = await session.get(Membership, (user.id, organization.id))
            identity = await session.scalar(
                select(UserIdentity).where(
                    UserIdentity.user_id == user.id,
                    UserIdentity.provider == IdentityProvider.LOCAL,
                )
            )
            if (
                user.status != "ACTIVE"
                or not user.email_verified_at
                or membership is None
                or membership.role != MembershipRole.ADMIN
                or membership.status != "ACTIVE"
                or identity is None
                or not identity.password_hash
            ):
                raise ValueError("Existing account is not this installation's active owner.")
            outcome = "unchanged"
        else:
            owner = await session.scalar(
                select(Membership.user_id).where(
                    Membership.organization_id == organization.id,
                    Membership.role == MembershipRole.ADMIN,
                )
            )
            if owner is not None:
                raise ValueError("An owner already exists; manage additional users in the Console.")
            user = User(email=email, status="ACTIVE", email_verified_at=datetime.now(UTC))
            session.add(user)
            await session.flush()
            session.add(
                UserIdentity(
                    user_id=user.id,
                    provider=IdentityProvider.LOCAL,
                    provider_subject=email,
                    password_hash=hash_password(payload.password),
                )
            )
            session.add(
                Membership(
                    user_id=user.id,
                    organization_id=organization.id,
                    role=MembershipRole.ADMIN,
                )
            )
            outcome = "created"
        return {
            "user_id": str(user.id),
            "organization_id": str(organization.id),
            "email": email,
            "result": outcome,
        }
