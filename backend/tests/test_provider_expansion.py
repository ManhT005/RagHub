import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError
from raghub_core.domain.providers.descriptor import ProviderDescriptor
from raghub_core.domain.providers.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
)

from app.modules.ai_providers.adapters.cloudflare_workers_ai import (
    CloudflareEmbeddingProvider,
    CloudflareRerankProvider,
)
from app.modules.ai_providers.adapters.http import ProviderHttp, response_error
from app.modules.ai_providers.adapters.huggingface import HuggingFaceEmbeddingProvider
from app.modules.ai_providers.adapters.siliconflow_rerank import SiliconFlowRerankProvider
from app.modules.ai_providers.adapters.voyage import VoyageEmbeddingProvider, VoyageRerankProvider
from app.modules.ai_providers.control_schemas import ConnectionInput
from app.modules.ai_providers.discovery import discover_models
from app.modules.ai_providers.policy import ProviderRequestPolicy
from app.modules.ai_providers.registry import ProviderRegistry
from app.modules.ai_providers.schemas import ProviderOptions, validate_connection_endpoint


def transport_with(data, captured):
    def handle(request):
        captured.append(request)
        return httpx.Response(200, json=data)

    return httpx.MockTransport(handle)


@pytest.mark.parametrize("model,contextual", [("voyage-4", False), ("voyage-context-4", True)])
async def test_voyage_preserves_indices_and_document_query_semantics(model, contextual):
    rows = [{"index": i, "embedding": [float(i), 0.5]} for i in [1, 0]]
    if contextual:
        rows = [{"index": row["index"], "data": [{**row, "index": 0}]} for row in rows]
    captured = []
    provider = VoyageEmbeddingProvider(
        base_url="https://api.voyageai.com/v1",
        model=model,
        dimension=2,
        secret="private-key",
        transport=transport_with({"data": rows, "usage": {"total_tokens": 7}}, captured),
    )
    assert await provider.embed_documents(["first", "second"]) == [[0.0, 0.5], [1.0, 0.5]]
    body = json.loads(captured[0].content)
    assert body["input_type"] == "document" and body["output_dimension"] == 2
    assert body["inputs" if contextual else "input"] == (
        [["first"], ["second"]] if contextual else ["first", "second"]
    )
    assert provider.last_usage["provider_reported_tokens"] == 7
    provider.transport = transport_with({"data": [rows[1]]}, captured)
    await provider.embed_query("question")
    assert json.loads(captured[-1].content)["input_type"] == "query"
    assert captured[-1].headers["authorization"] == "Bearer private-key"


@pytest.mark.parametrize("bad", [[[True, 0]], [[1]], [[[1, 2], [3, 4]]], [["x", 0]]])
async def test_hf_rejects_unpooled_or_invalid_vectors(bad):
    provider = HuggingFaceEmbeddingProvider(
        base_url="https://router.huggingface.co",
        model="intfloat/multilingual-e5-small",
        dimension=2,
        secret="hf-token",
        transport=transport_with(bad, []),
    )
    with pytest.raises(ProviderInvalidResponseError):
        await provider.embed_query("query")


async def test_hf_document_prefix_and_pooled_batch():
    captured = []
    provider = HuggingFaceEmbeddingProvider(
        base_url="https://router.huggingface.co",
        model="intfloat/multilingual-e5-small",
        dimension=2,
        secret="hf-token",
        transport=transport_with([[1, 2], [3, 4]], captured),
    )
    assert await provider.embed_documents(["a", "b"]) == [[1, 2], [3, 4]]
    assert json.loads(captured[0].content)["inputs"] == ["passage: a", "passage: b"]
    assert captured[0].url.path.endswith("/hf-inference/models/intfloat/multilingual-e5-small")


async def test_cloudflare_native_embedding_and_rerank_shape():
    captured = []
    kwargs = dict(
        base_url="https://api.cloudflare.com/client/v4/accounts/" + "a" * 32 + "/ai",
        secret="cf-token",
    )
    embedding = CloudflareEmbeddingProvider(
        **kwargs,
        model="@cf/baai/bge-base-en-v1.5",
        dimension=2,
        transport=transport_with({"success": True, "result": {"data": [[1, 2]]}}, captured),
    )
    assert await embedding.embed_query("text") == [1, 2]
    rerank = CloudflareRerankProvider(
        **kwargs,
        model="@cf/baai/bge-reranker-base",
        transport=transport_with(
            {"result": [{"id": 1, "score": 0.9}, {"id": 0, "score": 0.1}]}, captured
        ),
    )
    result = await rerank.rerank(query="question", documents=["a", "b"], top_n=2)
    assert [row.index for row in result.items] == [1, 0]
    assert json.loads(captured[-1].content)["contexts"] == [{"text": "a"}, {"text": "b"}]


@pytest.mark.parametrize(
    "provider_class,key,top",
    [
        (VoyageRerankProvider, "data", "top_k"),
        (SiliconFlowRerankProvider, "results", "top_n"),
    ],
)
async def test_rerank_profile_uses_vendor_payload_and_discards_returned_text(
    provider_class, key, top
):
    captured = []
    provider = provider_class(
        base_url="https://api.example.com/v1",
        model="rerank-model",
        secret="key",
        transport=transport_with(
            {
                key: [
                    {"index": 1, "relevance_score": 0.8, "document": {"text": "forged source"}},
                    {"index": 0, "relevance_score": 0.3},
                ]
            },
            captured,
        ),
    )
    result = await provider.rerank(query="q", documents=["original-a", "original-b"], top_n=2)
    assert [row.index for row in result.items] == [1, 0]
    assert not hasattr(result.items[0], "document")
    assert json.loads(captured[0].content)[top] == 2


@pytest.mark.parametrize(
    "rows",
    [
        [{"index": 0, "relevance_score": 0.2}, {"index": 0, "relevance_score": 0.9}],
        [{"index": 7, "relevance_score": 0.2}],
        [{"index": True, "relevance_score": 0.2}],
        [{"index": 0, "relevance_score": "high"}],
        [],
    ],
)
async def test_invalid_rerank_indices_scores_and_cardinality(rows):
    provider = VoyageRerankProvider(
        base_url="https://api.voyageai.com/v1",
        model="rerank-3",
        secret="key",
        transport=transport_with({"data": rows}, []),
    )
    with pytest.raises(ProviderInvalidResponseError):
        await provider.rerank(query="q", documents=["a", "b"], top_n=2)


@pytest.mark.parametrize(
    "status,error,attempts",
    [
        (401, ProviderAuthenticationError, 1),
        (403, ProviderAuthenticationError, 1),
        (404, ProviderConfigurationError, 1),
        (429, ProviderRateLimitError, 2),
        (400, ProviderInvalidResponseError, 1),
        (302, ProviderInvalidResponseError, 1),
    ],
)
async def test_http_error_sanitization_and_retry_bound(status, error, attempts):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "private-input private-key"})

    provider = ProviderHttp(
        base_url="https://api.example.com",
        secret="private-key",
        provider_name="TEST",
        policy=ProviderRequestPolicy(max_attempts=2, backoff_seconds=0),
        transport=httpx.MockTransport(handle),
    )
    with pytest.raises(error) as exc:
        await provider.request("/endpoint", {"input": "private-input"})
    assert len(calls) == attempts and "private" not in str(exc.value)


@pytest.mark.parametrize("value", ["NaN", "inf", "invalid"])
def test_nonfinite_retry_after_is_ignored(value):
    assert response_error(429, {"Retry-After": value}).details.get("retry_after_seconds", 0) == 0


@pytest.mark.parametrize(
    "catalog_id", ["groq", "openrouter", "cerebras", "siliconflow", "voyage", "huggingface"]
)
def test_brand_endpoints_cannot_be_retargeted(catalog_id):
    from app.modules.ai_providers.catalog import supported_catalog_by_id

    item = supported_catalog_by_id(catalog_id)
    with pytest.raises(ValidationError):
        ConnectionInput(
            name="test",
            catalog_id=catalog_id,
            provider_type=item.provider_type,
            base_url="https://other.example/v1",
        )
    connection = SimpleNamespace(
        catalog_id=catalog_id,
        provider_type=item.provider_type,
        base_url="https://other.example/v1",
        config_json={},
    )
    with pytest.raises(ValueError):
        validate_connection_endpoint(connection)


def test_cloudflare_builds_endpoint_from_account_and_never_accepts_header_injection():
    connection = ConnectionInput(
        name="CF",
        catalog_id="cloudflare-workers-ai",
        provider_type="CLOUDFLARE_WORKERS_AI",
        config_json={"account_id": "b" * 32},
    )
    assert connection.base_url.endswith("/accounts/" + "b" * 32 + "/ai")
    for value in ["hello\r\nAuthorization: injected", "☁"]:
        with pytest.raises(ValidationError):
            ProviderOptions(app_name=value)
    with pytest.raises(ValidationError):
        ProviderOptions(app_url="javascript:alert(1)")


async def test_hf_discovery_lists_only_live_served_embedding_models():
    def handle(request):
        assert request.headers["authorization"] == "Bearer personal-token"
        if request.url.path == "/api/whoami-v2":
            return httpx.Response(200, json={"name": "account"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "org/chat"}]})
        return httpx.Response(
            200,
            json=[
                {
                    "id": "org/live",
                    "inferenceProviderMapping": {
                        "hf-inference": {"status": "live", "task": "feature-extraction"}
                    },
                },
                {
                    "id": "org/staging",
                    "inferenceProviderMapping": {
                        "hf-inference": {"status": "staging", "task": "feature-extraction"}
                    },
                },
                {"id": "org/unavailable"},
            ],
        )

    connection = SimpleNamespace(
        catalog_id="huggingface",
        provider_type="HUGGINGFACE_INFERENCE",
        base_url="https://router.huggingface.co",
        config_json={},
    )
    models = await discover_models(
        connection, "personal-token", transport=httpx.MockTransport(handle)
    )
    assert [(model.model, model.capabilities) for model in models] == [
        ("org/chat", ["CHAT"]),
        ("org/live", ["EMBEDDING"]),
    ]


def test_siliconflow_rerank_cannot_be_used_with_custom_brand():
    descriptor = ProviderDescriptor(
        provider_type="OPENAI_COMPATIBLE",
        capability="RERANK",
        model="reranker",
        base_url="https://api.example.com/v1",
    )
    with pytest.raises(ProviderConfigurationError):
        ProviderRegistry().create(descriptor, "key")


async def test_siliconflow_capabilities_come_from_typed_upstream_lists():
    calls = []

    def handle(request):
        sub_type = request.url.params["sub_type"]
        calls.append(sub_type)
        return httpx.Response(200, json={"data": [{"id": "served/" + sub_type}]})

    connection = SimpleNamespace(
        provider_type="OPENAI_COMPATIBLE",
        catalog_id="siliconflow",
        base_url="https://api.siliconflow.com/v1",
        config_json={},
    )
    models = await discover_models(connection, "key", transport=httpx.MockTransport(handle))
    assert calls == ["chat", "embedding", "reranker"]
    assert [model.capabilities for model in models] == [["CHAT"], ["EMBEDDING"], ["RERANK"]]


async def test_cloud_legacy_api_cannot_mutate_connections_or_credentials(monkeypatch):
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from app.core.auth import OrganizationContext
    from app.core.exceptions import AppError
    from app.modules.ai_providers.router import create_provider, update_provider
    from app.modules.ai_providers.schemas import ProviderConfigInput, ProviderConfigPatch
    from app.modules.ai_providers.service import ProviderConfigService
    from app.modules.memberships.models import Membership, MembershipRole

    org = uuid4()
    context = OrganizationContext(org, Membership(role=MembershipRole.ADMIN, status="ACTIVE"))
    payload = ProviderConfigInput(
        name="cloud", provider_type="GOOGLE_GEMINI", capability="CHAT", model="gemini", secret="key"
    )
    with pytest.raises(AppError) as error:
        await create_provider(org, payload, context, None)
    assert error.value.code == "DEPRECATED_PROVIDER_API" and error.value.status_code == 410
    monkeypatch.setattr(
        ProviderConfigService,
        "get",
        AsyncMock(return_value=SimpleNamespace(provider_type="OPENAI_COMPATIBLE")),
    )
    with pytest.raises(AppError) as error:
        await update_provider(
            uuid4(),
            ProviderConfigPatch(base_url="https://other.example/v1", secret="other-key"),
            context,
            None,
        )
    assert error.value.code == "DEPRECATED_PROVIDER_API"


def test_snapshot_endpoint_cannot_exfiltrate_brand_credentials():
    from app.infrastructure.persistence.provider_descriptors import provider_descriptor
    from app.modules.ai_providers.models import (
        EmbeddingIndexVersion,
        ProviderConfig,
        ProviderConnection,
    )

    connection = ProviderConnection(
        catalog_id="openai",
        provider_type="OPENAI_COMPATIBLE",
        base_url="https://api.openai.com/v1",
        config_json={},
    )
    config = ProviderConfig(
        connection=connection,
        provider_type="OPENAI_COMPATIBLE",
        capability="EMBEDDING",
        model="m",
        dimension=2,
        base_url=connection.base_url,
        config_json={},
    )
    snapshot = EmbeddingIndexVersion(
        provider_type="OPENAI_COMPATIBLE",
        model="m",
        dimension=2,
        base_url="https://other.example/v1",
        config_json={},
    )
    with pytest.raises(ProviderConfigurationError):
        provider_descriptor(config, snapshot)
    connection.base_url += "/"
    snapshot.base_url = connection.base_url.rstrip("/")
    assert provider_descriptor(config, snapshot).base_url == snapshot.base_url


async def test_openrouter_public_catalog_cannot_mark_invalid_credentials_connected(monkeypatch):
    from unittest.mock import AsyncMock

    from app.modules.ai_providers.adapters.http import ProviderHttp
    from app.modules.ai_providers.control_service import ProviderControlService

    connection = SimpleNamespace(
        catalog_id="openrouter",
        provider_type="OPENAI_COMPATIBLE",
        base_url="https://openrouter.ai/api/v1",
        enabled=True,
        config_json={},
        status="UNTESTED",
    )
    service = object.__new__(ProviderControlService)
    service.get = AsyncMock(return_value=connection)
    service.secret = lambda _: "invalid-personal-key"
    service.session = SimpleNamespace(commit=AsyncMock())
    authentication = AsyncMock(side_effect=ProviderAuthenticationError())
    monkeypatch.setattr(ProviderHttp, "request", authentication)
    result = await service.test(None, None)
    assert result.status == "ERROR" and result.error_code == "PROVIDER_AUTH_FAILED"
    authentication.assert_awaited_once_with("/key", method="GET")
