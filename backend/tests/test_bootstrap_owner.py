import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import AppError
from app.infrastructure.persistence.bootstrap import BootstrapOwnerInput
from app.modules.auth.email import build_email_sender


def test_bootstrap_validates_credentials_without_disclosing_password():
    with pytest.raises(ValidationError):
        BootstrapOwnerInput(email="owner@example.com", password="short")
    payload = BootstrapOwnerInput(email="owner@example.com", password="strong-test-password")
    assert "strong-test-password" not in repr(payload)


async def test_selfhost_without_smtp_cannot_log_reset_tokens(monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="selfhost",
        provider_master_key="test-master-key",
        app_secret_key="selfhost-test-key-at-least-32-characters",
    )
    warning = AsyncMock()
    monkeypatch.setattr("app.modules.auth.email.logger.warning", warning)
    with pytest.raises(AppError, match="Configure SMTP"):
        await build_email_sender(settings).send("owner@example.com", "Reset", "secret-token")
    warning.assert_not_called()


@pytest.mark.integration
async def test_bootstrap_preserves_owner_password_and_rolls_back_unrelated_identity():
    from sqlalchemy import delete, func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.infrastructure.persistence.bootstrap import bootstrap_owner
    from app.modules.auth.models import UserIdentity
    from app.modules.organizations.models import Organization
    from app.modules.users.models import User

    url = os.getenv("RAGHUB_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set RAGHUB_TEST_DATABASE_URL.")
    engine = create_async_engine(url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    slug = f"bootstrap-{suffix}"
    email = f"bootstrap-{suffix}@example.com"
    payload = BootstrapOwnerInput(
        email=email, password="original-test-password", organization_slug=slug
    )
    try:
        async with sessions() as session:
            first = await bootstrap_owner(session, payload)
            original = await session.scalar(
                select(UserIdentity.password_hash).join(User).where(User.email == email)
            )
            await session.rollback()
            again = await bootstrap_owner(
                session, payload.model_copy(update={"password": "changed-test-password"})
            )
            assert first["result"] == "created" and again["result"] == "unchanged"
            assert first["user_id"] == again["user_id"]
            assert (
                await session.scalar(
                    select(UserIdentity.password_hash).join(User).where(User.email == email)
                )
                == original
            )
            await session.rollback()
            # Reusing an unrelated identity must not elevate it or leave an orphan organization.
            with pytest.raises(ValueError, match="Existing account"):
                await bootstrap_owner(
                    session, payload.model_copy(update={"organization_slug": slug + "-other"})
                )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Organization)
                    .where(Organization.slug == slug + "-other")
                )
                == 0
            )
    finally:
        async with sessions() as session:
            await session.execute(
                delete(Organization).where(Organization.slug.in_([slug, slug + "-other"]))
            )
            await session.execute(delete(User).where(User.email == email))
            await session.commit()
        await engine.dispose()
