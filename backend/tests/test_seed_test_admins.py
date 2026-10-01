import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.modules.auth.models import UserIdentity
from app.modules.auth.service import AuthService
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.users.models import User
from app.seed_test_admins import SeedInput, seed_admins


def test_rejects_duplicate_accounts_and_short_passwords():
    with pytest.raises(ValidationError):
        SeedInput(
            accounts=[
                {"email": "admin@example.com", "password": "example-password"},
                {"email": "ADMIN@example.com", "password": "example-password"},
            ]
        )
    with pytest.raises(ValidationError):
        SeedInput(
            accounts=[
                {"email": "admin1@example.com", "password": "short"},
                {"email": "admin2@example.com", "password": "example-password"},
            ]
        )


@pytest.mark.integration
async def test_seed_login_idempotency_and_atomic_conflict():
    url = os.getenv("RAGHUB_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set RAGHUB_TEST_DATABASE_URL.")
    engine = create_async_engine(url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    slug = f"seed-{suffix}"
    emails = [f"admin-{i}-{suffix}@example.com" for i in range(3)]
    payload = SeedInput(
        organization_slug=slug,
        accounts=[{"email": email, "password": "test-only-password"} for email in emails[:2]],
    )
    try:
        async with sessions() as session:
            result = await seed_admins(session, payload)
            assert [item["result"] for item in result["accounts"]] == ["created", "created"]
            hashes = list(
                (
                    await session.scalars(
                        select(UserIdentity.password_hash).join(User).where(User.email.in_(emails))
                    )
                ).all()
            )
            await session.rollback()
            changed_passwords = payload.model_copy(
                update={
                    "accounts": [
                        item.model_copy(update={"password": "different-test-password"})
                        for item in payload.accounts
                    ]
                }
            )
            again = await seed_admins(session, changed_passwords)
            assert again["organization_id"] == result["organization_id"]
            assert again["workspace_id"] == result["workspace_id"]
            assert all(item["result"] == "unchanged" for item in again["accounts"])
            assert (
                list(
                    (
                        await session.scalars(
                            select(UserIdentity.password_hash)
                            .join(User)
                            .where(User.email.in_(emails))
                        )
                    ).all()
                )
                == hashes
            )
            roles = list(
                (
                    await session.scalars(
                        select(Membership.role).join(User).where(User.email.in_(emails))
                    )
                ).all()
            )
            assert roles == ["ADMIN", "ADMIN"]
            for email in emails[:2]:
                auth = AuthService(
                    session=session, email_sender=AsyncMock(), settings=Settings(_env_file=None)
                )
                assert (await auth.login(email, "test-only-password")).access_token
            # A conflicting second account rolls back the newly created first one and organization.
            conflict_slug = f"conflict-{suffix}"
            conflict = SeedInput(
                organization_slug=conflict_slug,
                accounts=[
                    {"email": emails[2], "password": "test-only-password"},
                    {"email": emails[0], "password": "test-only-password"},
                ],
            )
            with pytest.raises(ValueError, match="Existing account"):
                await seed_admins(session, conflict)
            assert (
                await session.scalar(
                    select(func.count()).select_from(User).where(User.email == emails[2])
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Organization)
                    .where(Organization.slug == conflict_slug)
                )
                == 0
            )
    finally:
        async with sessions() as session:
            await session.execute(
                delete(Organization).where(Organization.slug.in_([slug, f"conflict-{suffix}"]))
            )
            await session.execute(delete(User).where(User.email.in_(emails)))
            await session.commit()
        await engine.dispose()
