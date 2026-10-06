import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.infrastructure.task_queue.celery_app import celery_app
from app.modules.ai_providers.control_schemas import DiscoveredModel, OllamaPullInput
from app.modules.ai_providers.control_service import ProviderControlService
from app.modules.ai_providers.models import OllamaModelPull, ProviderConfig, ProviderConnection
from app.modules.ai_providers.ollama_manager import OllamaModelManager, ollama_connection
from app.modules.organizations.models import Organization


@pytest.fixture
async def ollama_connection_row(isolated_sessions):
    async with isolated_sessions() as session:
        organization = Organization(name="Test", slug="ollama-manager")
        session.add(organization)
        await session.flush()
        connection = ProviderConnection(
            organization_id=organization.id,
            provider_type="OLLAMA",
            catalog_id="ollama",
            name="Local",
            base_url="http://ollama:11434",
            enabled=True,
            config_json={},
        )
        session.add(connection)
        await session.commit()
        return organization.id, connection.id


def test_pull_only_allows_ollama_and_safe_model_names():
    with pytest.raises(AppError, match="requires Ollama"):
        ollama_connection(ProviderConnection(provider_type="OPENAI_COMPATIBLE", enabled=True))
    for model in ("https://evil/model", "../../secret", "model?secret=value", "model\nname"):
        with pytest.raises(ValidationError):
            OllamaPullInput(model=model)
    assert OllamaPullInput(model="qwen3:4b").register_after_pull


@pytest.mark.integration
async def test_pull_is_queued_scoped_and_idempotent(
    isolated_sessions, ollama_connection_row, monkeypatch
):
    org, connection = ollama_connection_row
    queue = Mock()
    monkeypatch.setattr(celery_app, "send_task", queue)
    async with isolated_sessions() as session:
        manager = OllamaModelManager(session)
        job = await manager.start(org, connection, OllamaPullInput(model="gemma3:1b"))
        assert job.status == "QUEUED"
        again = await manager.start(org, connection, OllamaPullInput(model="gemma3:1b"))
        assert again.id == job.id
        queue.assert_called_once()
        with pytest.raises(AppError) as error:
            await manager.start(org, connection, OllamaPullInput(model="qwen3:4b"))
        assert error.value.code == "MODEL_PULL_IN_PROGRESS"
        with pytest.raises(AppError) as error:
            await manager.get(uuid4(), connection, job.id)
        assert error.value.code == "MODEL_PULL_NOT_FOUND"


@pytest.mark.integration
@pytest.mark.parametrize("failure", [False, True])
async def test_stream_progress_and_failure_are_persisted(
    isolated_sessions, ollama_connection_row, monkeypatch, failure
):
    org, connection = ollama_connection_row
    monkeypatch.setattr(celery_app, "send_task", Mock())
    monkeypatch.setattr(
        ProviderControlService,
        "discover",
        AsyncMock(return_value=[DiscoveredModel(model="gemma3:1b", capabilities=["CHAT"])]),
    )
    async with isolated_sessions() as session:
        manager = OllamaModelManager(session)
        job = await manager.start(
            org, connection, OllamaPullInput(model="gemma3:1b", register_after_pull=False)
        )
        events = [
            {"status": "pulling layer", "digest": "sha256:a", "total": 100, "completed": 60},
            {"status": "pulling layer", "digest": "sha256:a", "total": 100, "completed": 100},
            {"error": "upstream-secret"} if failure else {"status": "success"},
        ]

        def respond(request):
            assert request.url.path == "/api/pull"
            assert json.loads(request.content) == {"model": "gemma3:1b", "stream": True}
            return httpx.Response(200, text="\n".join(json.dumps(event) for event in events))

        await manager.run(job.id, transport=httpx.MockTransport(respond))
        await session.refresh(job)
        assert job.status == ("FAILED" if failure else "READY")
        assert job.total_bytes == 100
        assert "upstream-secret" not in str(job.error_code)
        if not failure:
            assert job.completed_bytes == 100
        # A fresh session can resume UI polling after an API restart.
        job_id = job.id
    async with isolated_sessions() as session:
        assert (await session.get(OllamaModelPull, job_id)).status in {"READY", "FAILED"}


@pytest.mark.integration
async def test_install_register_uses_the_regular_health_checked_registry(
    isolated_sessions, ollama_connection_row, monkeypatch
):
    org, connection_id = ollama_connection_row
    monkeypatch.setattr(celery_app, "send_task", Mock())
    monkeypatch.setattr(
        ProviderControlService,
        "discover",
        AsyncMock(return_value=[DiscoveredModel(model="gemma3:1b", capabilities=["CHAT"])]),
    )
    from app.modules.ai_providers.service import ProviderConfigService

    health = AsyncMock()
    monkeypatch.setattr(ProviderConfigService, "test", health)
    async with isolated_sessions() as session:
        manager = OllamaModelManager(session)
        job = await manager.start(org, connection_id, OllamaPullInput(model="gemma3:1b"))
        await manager.run(
            job.id,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text='{"status":"success"}\n')
            ),
        )
        await session.refresh(job)
        assert job.status == "READY" and job.registered_model_id
        model = await session.get(ProviderConfig, job.registered_model_id)
        assert model.connection_id == connection_id and model.capability == "CHAT"
        health.assert_awaited_once_with(org, model.id)
