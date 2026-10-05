from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.modules.ai_providers.models import ProviderConfig, ProviderConnection
from app.modules.ai_providers.service import ProviderConfigService
from app.modules.installation.local_ai_bootstrap import LocalAiBootstrapService
from app.modules.organizations.models import Organization, OrganizationAiDefaults


@pytest.mark.integration
async def test_local_defaults_are_idempotent_and_survive_failed_health(
    isolated_sessions, monkeypatch
):
    async with isolated_sessions() as session:
        organization = Organization(name="Test", slug="local-bootstrap")
        session.add(organization)
        await session.flush()
        service = LocalAiBootstrapService(session)
        first = await service.ensure(organization.id)
        second = await service.ensure(organization.id)
        assert [model.id for model in first] == [model.id for model in second]
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(ProviderConnection)) == 2
        assert await session.scalar(select(func.count()).select_from(ProviderConfig)) == 2
        monkeypatch.setattr(ProviderConfigService, "test", AsyncMock(side_effect=TimeoutError()))
        await service.health_check(organization.id, [model.id for model in first])
        assert all(model.availability_status == "UNAVAILABLE" for model in first)
        defaults = await session.get(OrganizationAiDefaults, organization.id)
        assert defaults.default_embedding_model_id == first[0].id
        assert defaults.default_chat_model_id == first[1].id


async def test_probe_failure_is_persisted_without_undoing_setup(monkeypatch):
    config = SimpleNamespace(connection=SimpleNamespace())
    monkeypatch.setattr(ProviderConfigService, "get", AsyncMock(return_value=config))
    monkeypatch.setattr(ProviderConfigService, "test", AsyncMock(side_effect=TimeoutError()))
    session = SimpleNamespace(commit=AsyncMock())
    await LocalAiBootstrapService(session).health_check(uuid4(), [uuid4()])
    assert config.availability_status == "UNAVAILABLE"
    assert config.connection.status == "DEGRADED"
    session.commit.assert_awaited_once()


@pytest.mark.integration
async def test_workspace_defaults_bind_both_models_and_explicit_null_skips_them(isolated_sessions):
    from app.core.auth import OrganizationContext
    from app.modules.workspaces.router import WorkspaceCreateInput, create_workspace

    async with isolated_sessions() as session:
        organization = Organization(name="Test", slug="workspace-defaults")
        session.add(organization)
        await session.flush()
        configs = await LocalAiBootstrapService(session).ensure(organization.id)
        for config in configs:
            config.availability_status = "AVAILABLE"
            config.connection.status = "CONNECTED"
        await session.commit()
        context = OrganizationContext(
            organization.id, SimpleNamespace(role="ADMIN", status="ACTIVE")
        )
        created = await create_workspace(
            WorkspaceCreateInput(name="Default", slug="with-defaults"), context, session
        )
        assert created.ai_status == "READY"
        assert created.chat_model["model"] == "gemma3:1b"
        assert created.embedding_model["dimension"] == 384
        empty = await create_workspace(
            WorkspaceCreateInput(
                name="Empty", slug="without-defaults", embedding_model_id=None, chat_model_id=None
            ),
            context,
            session,
        )
        assert empty.ai_status == "NOT_CONFIGURED"


@pytest.mark.integration
async def test_bound_legacy_local_connection_can_be_retested_without_runtime_change(
    isolated_sessions,
):
    from app.core.auth import OrganizationContext
    from app.core.exceptions import AppError
    from app.modules.ai_providers.control_schemas import ConnectionPatch
    from app.modules.ai_providers.control_service import ProviderControlService
    from app.modules.workspaces.router import WorkspaceCreateInput, create_workspace

    async with isolated_sessions() as session:
        organization = Organization(name="Legacy", slug="legacy-local")
        session.add(organization)
        await session.flush()
        configs = await LocalAiBootstrapService(session).ensure(organization.id)
        chat = configs[1]
        chat.availability_status = "AVAILABLE"
        chat.connection.status = "CONNECTED"
        chat.connection.config_json = {}
        chat.config_json = {}
        await session.commit()
        context = OrganizationContext(
            organization.id, SimpleNamespace(role="ADMIN", status="ACTIVE")
        )
        await create_workspace(
            WorkspaceCreateInput(name="Chat", slug="legacy-chat", embedding_model_id=None),
            context,
            session,
        )
        service = ProviderControlService(session)
        await service.update(
            organization.id,
            chat.connection_id,
            ConnectionPatch(name="Local Chat", catalog_id="ollama", base_url=chat.base_url),
        )
        assert chat.availability_status == "AVAILABLE"
        assert chat.connection.status == "CONNECTED"
        with pytest.raises(AppError) as error:
            await service.update(
                organization.id,
                chat.connection_id,
                ConnectionPatch(base_url="http://localhost:11434"),
            )
        assert error.value.code == "PROVIDER_IN_USE"
