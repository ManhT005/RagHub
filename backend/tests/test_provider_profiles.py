import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.persistence.provider_descriptors import provider_descriptor
from app.modules.ai_providers.adapters.openai_compatible import OpenAICompatibleEmbeddingProvider
from app.modules.ai_providers.control_schemas import ConnectionInput
from app.modules.ai_providers.control_service import infer_dimension
from app.modules.ai_providers.discovery import discover_models
from app.modules.ai_providers.models import ProviderConfig, ProviderConnection
from app.modules.ai_providers.registry import ProviderRegistry
from app.modules.ai_providers.schemas import validate_trusted_local_provider_url


@pytest.fixture
def local_hosts(monkeypatch):
    settings = Settings(
        _env_file=None, trusted_local_provider_hosts="host.docker.internal,9router,metadata"
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port: [
            (
                None,
                None,
                None,
                None,
                ("169.254.169.254" if host == "metadata" else "192.168.1.5", 80),
            )
        ],
    )


def test_exact_trusted_hosts_and_public_policy_are_separate(local_hosts):
    connection = ConnectionInput(
        name="Gateway", catalog_id="9router", provider_type="OPENAI_COMPATIBLE"
    )
    assert connection.base_url == "http://9router:20128/v1"
    assert connection.config_json["endpoint_scope"] == "LOCAL_TRUSTED"
    for url in (
        "http://9router.evil/v1",
        "http://10.1.2.3/v1",
        "http://169.254.169.254/latest",
        "http://metadata/v1",
        "http://9router@evil/v1",
    ):
        with pytest.raises(ValueError):
            validate_trusted_local_provider_url(url)
    with pytest.raises(ValidationError):
        ConnectionInput(
            name="Public",
            catalog_id="compatible",
            provider_type="OPENAI_COMPATIBLE",
            base_url="http://9router:20128/v1",
            config_json={"endpoint_scope": "LOCAL_TRUSTED"},
        )


async def test_local_gateway_discovery_preserves_unknown_capability(local_hosts):
    connection = ProviderConnection(
        provider_type="OPENAI_COMPATIBLE", catalog_id="9router", base_url="http://9router:20128/v1"
    )
    models = await discover_models(
        connection,
        "private-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "unknown"}]})
        ),
    )
    assert models[0].capabilities == []


async def test_nvidia_profile_applies_query_and_passage_through_registry(monkeypatch):
    connection = ConnectionInput(
        name="NIM", catalog_id="nvidia-nim", provider_type="OPENAI_COMPATIBLE"
    )
    model = ProviderConfig(
        model="nvidia/nv-embedqa-e5-v5",
        provider_type="OPENAI_COMPATIBLE",
        capability="EMBEDDING",
        dimension=2,
        base_url=connection.base_url,
        config_json=connection.config_json,
    )
    provider = ProviderRegistry().create(provider_descriptor(model), "secret")
    assert isinstance(provider, OpenAICompatibleEmbeddingProvider)
    requests = []
    real_client = httpx.AsyncClient

    def response(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(response)),
    )
    assert await provider.embed_query("Question") == [1.0, 0.0]
    assert await provider.embed_documents(["Document"]) == [[1.0, 0.0]]
    assert [request["input_type"] for request in requests] == ["query", "passage"]
    assert all(request["encoding_format"] == "float" for request in requests)


async def test_nvidia_dimension_probe_uses_query_profile(monkeypatch):
    connection = SimpleNamespace(
        provider_type="OPENAI_COMPATIBLE",
        catalog_id="nvidia-nim",
        base_url="https://integrate.api.nvidia.com/v1",
    )
    requests = []
    real_client = httpx.AsyncClient

    def response(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0]}]})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(response)),
    )
    assert await infer_dimension(connection, "nvidia/embed", "secret") == 2
    assert requests[0]["input_type"] == "query"
