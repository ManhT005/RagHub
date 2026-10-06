from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.auth import OrganizationContext, get_organization_context
from app.core.database import get_session
from app.core.exceptions import AppError
from app.infrastructure.provider_credentials import resolve_provider_secret
from app.main import app
from app.modules.ai_providers.catalog import CATALOG
from app.modules.ai_providers.control_schemas import ConnectionInput
from app.modules.ai_providers.control_service import connection_response, model_response
from app.modules.ai_providers.discovery import discover_models
from app.modules.ai_providers.models import ProviderConfig, ProviderConnection


def test_catalog_and_connection_validation():
    supported = [item for item in CATALOG if item.status == "SUPPORTED"]
    assert all(item.provider_type for item in supported)
    assert not any("RERANKER" in item.capabilities for item in CATALOG)
    gemini = ConnectionInput(name="Google", provider_type="GOOGLE_GEMINI", catalog_id="gemini")
    assert gemini.base_url.endswith("/v1beta/openai")
    with pytest.raises(AppError):
        ConnectionInput(name="unsupported", provider_type="ANTHROPIC", catalog_id="anthropic")
    with pytest.raises(ValidationError):
        ConnectionInput(
            name="unsafe",
            provider_type="OPENAI_COMPATIBLE",
            catalog_id="compatible",
            base_url="http://127.0.0.1",
        )
    with pytest.raises(ValidationError):
        ConnectionInput(
            name="unsafe",
            provider_type="GOOGLE_GEMINI",
            catalog_id="gemini",
            config_json={"nested": {"api_key": "secret"}},
        )
    assert (
        ConnectionInput(name="local", provider_type="OLLAMA", catalog_id="ollama").base_url
        == "http://ollama:11434"
    )


def test_secrets_are_connection_owned_and_never_serialized():
    now = datetime.now(UTC)
    connection = ProviderConnection(
        id=uuid4(),
        organization_id=uuid4(),
        name="Google",
        provider_type="GOOGLE_GEMINI",
        base_url="https://provider.test/v1",
        enabled=True,
        encrypted_secret="ciphertext",
        config_json={},
        status="CONNECTED",
        created_at=now,
        updated_at=now,
    )
    model = ProviderConfig(
        id=uuid4(),
        connection=connection,
        connection_id=connection.id,
        organization_id=connection.organization_id,
        name="model",
        model="model",
        provider_type=connection.provider_type,
        capability="CHAT",
        availability_status="AVAILABLE",
        enabled=True,
    )
    cipher = SimpleNamespace(
        decrypt=lambda value: "connection-secret" if value == "ciphertext" else "legacy-secret"
    )
    assert resolve_provider_secret(model, cipher) == "connection-secret"
    for data in (connection_response(connection).model_dump(), model_response(model).model_dump()):
        assert "encrypted_secret" not in data and "secret" not in data
        assert "ciphertext" not in str(data) and "connection-secret" not in str(data)


async def test_gemini_discovery_pagination_and_capabilities():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.params.get("pageToken"):
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]}
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "models/chat", "supportedGenerationMethods": ["generateContent"]}
                ],
                "nextPageToken": "next",
            },
        )

    connection = SimpleNamespace(
        provider_type="GOOGLE_GEMINI",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai"
    )
    models = await discover_models(
        connection, "private-key", transport=httpx.MockTransport(handler)
    )
    assert models[0].capabilities == ["CHAT"] and models[1].capabilities == ["EMBEDDING"]
    assert requests[0].url.path == "/v1beta/models"
    assert requests[0].headers["x-goog-api-key"] == "private-key"
    assert "private-key" not in str(requests[0].url)


async def test_discovery_failure_is_sanitized_and_manual_mode_is_explicit():
    connection = SimpleNamespace(
        provider_type="OPENAI_COMPATIBLE", base_url="https://provider.test/v1"
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, text="private upstream body")
    )
    with pytest.raises(AppError) as error:
        await discover_models(connection, "key", transport=transport)
    assert error.value.code == "PROVIDER_AUTH_FAILED"
    assert "private upstream body" not in str(error.value)
    connection.provider_type = "LOCAL_SENTENCE_TRANSFORMER"
    with pytest.raises(AppError) as error:
        await discover_models(connection, None)
    assert error.value.code == "MODEL_DISCOVERY_UNSUPPORTED"


def test_delegated_members_cannot_administer_connection_or_models():
    context = OrganizationContext(uuid4(), SimpleNamespace(role="WORKSPACE_ADMIN", user_id=uuid4()))
    app.dependency_overrides[get_organization_context] = lambda: context
    app.dependency_overrides[get_session] = lambda: SimpleNamespace()
    try:
        with TestClient(app) as client:
            for path in (
                "ai/provider-catalog",
                f"organizations/{context.organization_id}/provider-connections",
                f"organizations/{context.organization_id}/models",
                f"models/{uuid4()}",
            ):
                assert client.get(f"/api/v1/{path}").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_validation_errors_never_echo_credentials():
    context = OrganizationContext(uuid4(), SimpleNamespace(role="ADMIN"))
    app.dependency_overrides[get_organization_context] = lambda: context
    app.dependency_overrides[get_session] = lambda: SimpleNamespace()
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/organizations/{context.organization_id}/provider-connections",
                json={
                    "name": "local",
                    "provider_type": "OLLAMA",
                    "catalog_id": "ollama",
                    "secret": "private-password",
                },
            )
            assert response.status_code == 422
            assert "private-password" not in response.text
    finally:
        app.dependency_overrides.clear()
