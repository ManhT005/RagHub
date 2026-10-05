import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.exceptions import AppError
from app.core.security import verify_password
from app.infrastructure.persistence.bootstrap import BootstrapOwnerInput, bootstrap_owner
from app.main import app
from app.modules.ai_providers.models import ProviderConfig
from app.modules.auth.models import UserIdentity, UserSession
from app.modules.auth.service import AuthService
from app.modules.installation.models import InstallationState
from app.modules.installation.schemas import InitializeInstallationInput
from app.modules.installation.service import InitializeInstallationService
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.users.models import User


def payload(**kwargs):
    return InitializeInstallationInput(
        owner_email="owner@example.com", owner_password="original-password", **kwargs
    )


@pytest.fixture
async def installation_sessions(isolated_sessions):
    async with isolated_sessions() as session:
        session.add(InstallationState(id=1, status="UNINITIALIZED"))
        await session.commit()
    return isolated_sessions


def test_setup_rejects_infrastructure_secrets_and_preserves_password_spaces():
    with pytest.raises(ValidationError):
        payload(APP_SECRET_KEY="infrastructure-secret")
    assert payload().owner_password not in repr(payload())
    model = InitializeInstallationInput(
        owner_email="owner@example.com", owner_password="  spaced-password  "
    )
    assert model.owner_password == "  spaced-password  "


@pytest.mark.integration
async def test_atomic_initialize_and_cli_idempotency(installation_sessions):
    sessions = installation_sessions
    async with sessions() as session:
        result = await InitializeInstallationService(session).initialize(payload())
        assert (await session.get(InstallationState, 1)).status == "INITIALIZED"
        assert await session.scalar(select(func.count()).select_from(Membership)) == 1
        identity = await session.scalar(select(UserIdentity))
        original_hash = identity.password_hash
        assert verify_password("original-password", original_hash)
        await session.rollback()
        again = await bootstrap_owner(
            session, BootstrapOwnerInput(email="owner@example.com", password="different-password")
        )
        assert again["result"] == "unchanged" and again["user_id"] == result.user_id
        assert (await session.scalar(select(UserIdentity))).password_hash == original_hash
        await session.rollback()
        with pytest.raises(AppError) as error:
            await InitializeInstallationService(session).initialize(payload())
        assert error.value.code == "INSTALLATION_ALREADY_INITIALIZED"
        with pytest.raises(ValueError):
            await bootstrap_owner(
                session,
                BootstrapOwnerInput(
                    email="other@example.com",
                    password="different-password",
                    organization_slug="other",
                ),
            )
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert await session.scalar(select(func.count()).select_from(Organization)) == 1


@pytest.mark.integration
async def test_failed_session_creation_rolls_back_everything(installation_sessions):
    async with installation_sessions() as session:
        auth = AsyncMock()
        auth.issue_session.side_effect = RuntimeError("injected failure")
        with pytest.raises(RuntimeError):
            await InitializeInstallationService(session).initialize(payload(), auth_service=auth)
        assert (await session.get(InstallationState, 1)).status == "UNINITIALIZED"
        for model in (User, UserIdentity, Organization, Membership, UserSession):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.integration
async def test_concurrent_initialization_only_one_owner(installation_sessions):
    async def initialize():
        async with installation_sessions() as session:
            return await InitializeInstallationService(session).initialize(payload())

    results = await asyncio.gather(initialize(), initialize(), return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in results) == 1
    rejected = next(result for result in results if isinstance(result, Exception))
    assert isinstance(rejected, AppError) and rejected.code == "INSTALLATION_ALREADY_INITIALIZED"
    async with installation_sessions() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert await session.scalar(select(func.count()).select_from(Membership)) == 1


@pytest.mark.integration
async def test_local_ai_configs_and_auth_session_commit_together(installation_sessions):
    async with installation_sessions() as session:
        auth = AuthService(
            session=session, email_sender=AsyncMock(), settings=Settings(_env_file=None)
        )
        result = await InitializeInstallationService(session).initialize(
            payload(ai_mode="LOCAL"), auth_service=auth
        )
        assert result.auth and len(result.provider_ids) == 2
        providers = list(await session.scalars(select(ProviderConfig)))
        assert {provider.provider_type for provider in providers} == {
            "LOCAL_SENTENCE_TRANSFORMER",
            "OLLAMA",
        }
        assert await session.scalar(select(func.count()).select_from(UserSession)) == 1


@pytest.mark.integration
async def test_setup_http_handoff_cookie_status_and_takeover(installation_sessions, monkeypatch):
    async def override_session():
        async with installation_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    monkeypatch.setattr("app.core.auth.get_settings", lambda: Settings(_env_file=None))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            status = await client.get("/api/v1/setup/status")
            assert status.json() == {"status": "UNINITIALIZED", "initialized": False}
            assert status.headers["cache-control"] == "no-store"
            response = await client.post("/api/v1/setup/initialize", json=payload().model_dump())
            assert response.status_code == 201
            assert "HttpOnly" in response.headers["set-cookie"]
            token = response.json()["access_token"]
            assert (
                await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            ).status_code == 200
            assert (await client.post("/api/v1/auth/refresh")).status_code == 200
            assert (await client.get("/api/v1/setup/status")).json()["initialized"]
            response = await client.post("/api/v1/setup/initialize", json=payload().model_dump())
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "INSTALLATION_ALREADY_INITIALIZED"
    finally:
        app.dependency_overrides.clear()
