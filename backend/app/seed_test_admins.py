"""Explicit, one-time test account provisioning; never runs at application startup."""

import asyncio
import json
import sys
from datetime import UTC, datetime

from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401
from app.core.database import SessionFactory, engine
from app.core.security import hash_password
from app.modules.auth.models import IdentityProvider, UserIdentity
from app.modules.memberships.models import Membership, MembershipRole
from app.modules.organizations.models import Organization
from app.modules.users.models import User
from app.modules.workspaces.models import Workspace


class TestAdmin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128, repr=False)


class SeedInput(BaseModel):
    organization_slug: str = Field(default="raghub-shared-test", pattern=r"^[a-z0-9-]{1,100}$")
    organization_name: str = Field(default="RagHub Shared Test", min_length=1, max_length=200)
    accounts: list[TestAdmin] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def distinct_emails(self):
        if len({str(account.email).lower() for account in self.accounts}) != 2:
            raise ValueError("Provide two distinct email addresses.")
        return self


async def seed_admins(session: AsyncSession, payload: SeedInput) -> dict:
    """Provision atomically, refusing to adopt or elevate existing unrelated users."""
    async with session.begin():
        # Serialize concurrent invocations, including different organizations sharing emails.
        await session.execute(text("SELECT pg_advisory_xact_lock(7291042026)"))
        organization = await session.scalar(
            select(Organization).where(Organization.slug == payload.organization_slug)
        )
        if organization is None:
            organization = Organization(
                name=payload.organization_name, slug=payload.organization_slug, status="ACTIVE"
            )
            session.add(organization)
            await session.flush()
        elif organization.status != "ACTIVE":
            raise ValueError("The test organization is not active.")

        results = []
        for account in payload.accounts:
            email = str(account.email).lower()
            user = await session.scalar(select(User).where(func.lower(User.email) == email))
            if user is None:
                user = User(email=email, status="ACTIVE", email_verified_at=datetime.now(UTC))
                session.add(user)
                await session.flush()
                session.add(
                    UserIdentity(
                        user_id=user.id,
                        provider=IdentityProvider.LOCAL,
                        provider_subject=email,
                        password_hash=hash_password(account.password),
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
            else:
                membership = await session.get(Membership, (user.id, organization.id))
                identity = await session.scalar(
                    select(UserIdentity).where(
                        UserIdentity.user_id == user.id,
                        UserIdentity.provider == IdentityProvider.LOCAL,
                    )
                )
                if (
                    user.status != "ACTIVE"
                    or membership is None
                    or membership.role != MembershipRole.ADMIN
                    or identity is None
                    or not identity.password_hash
                ):
                    raise ValueError(
                        f"Existing account {email} is not an active test admin "
                        "in this organization."
                    )
                outcome = "unchanged"
            results.append({"email": email, "role": "ADMIN", "result": outcome})

        workspace = await session.scalar(
            select(Workspace).where(
                Workspace.organization_id == organization.id, Workspace.slug == "shared-test"
            )
        )
        if workspace is None:
            workspace = Workspace(
                organization_id=organization.id, name="Shared Test", slug="shared-test"
            )
            session.add(workspace)
        elif workspace.deleted_at is not None:
            raise ValueError("The shared test workspace has been deleted.")
        await session.flush()
        return {
            "organization_id": str(organization.id),
            "workspace_id": str(workspace.id),
            "accounts": results,
        }


async def main() -> int:
    try:
        # Use stdin so passwords are absent from image layers, argv, and Docker configuration.
        payload = SeedInput.model_validate_json(sys.stdin.read())
        async with SessionFactory() as session:
            result = await seed_admins(session, payload)
        print(json.dumps(result))
        return 0
    except ValueError:
        print(
            "Seed rejected: check the input and existing test account permissions.", file=sys.stderr
        )
        return 1
    except Exception:
        print(
            "Seed failed; no changes committed. Check database connectivity and migrations.",
            file=sys.stderr,
        )
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
