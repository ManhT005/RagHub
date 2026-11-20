import json
from types import SimpleNamespace

import httpx
import pytest
from raghub_core.domain.providers.contracts import ChatMessage, ChatOptions
from raghub_core.domain.providers.descriptor import ProviderDescriptor
from raghub_core.domain.providers.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderInvalidResponseError,
)

from app.modules.ai_providers.adapters.spaces import (
    SpaceClient,
    SpacesChatProvider,
    SpacesEmbeddingProvider,
    extract,
    mapping,
    space_origin,
)
from app.modules.ai_providers.control_schemas import ConnectionInput
from app.modules.ai_providers.discovery import discover_models
from app.modules.ai_providers.registry import ProviderRegistry


@pytest.mark.parametrize("event", ["complete", "error"])
async def test_sict_quota_is_not_misreported_as_output_mapping(event):
    from raghub_core.domain.providers.errors import ProviderRateLimitError

    private = "hf_secret_never_echo"
    body = {
        "status": "error",
        "error_code": "INFERENCE_FAILED",
        "message": "You have exceeded your ZeroGPU runs limit " + private,
    }

    def handle(request):
        assert request.headers["Authorization"] == "Bearer " + private
        if request.method == "POST":
            return httpx.Response(200, json={"event_id": "abc"})
        data = [body] if event == "complete" else body
        return httpx.Response(200, text=f"event: {event}\ndata: {json.dumps(data)}\n\n")

    client = SpaceClient("https://test.hf.space", private, httpx.MockTransport(handle))
    with pytest.raises(ProviderRateLimitError) as exc:
        await client.call({"api": "embed_batch_text", "inputs": [], "output": "0.embeddings"}, {})
    assert private not in str(exc.value)


async def test_sict_real_success_shape_yields_1024_vectors_for_query_and_document():
    provider = SpacesEmbeddingProvider(
        base_url="https://quyendzvaio-sict.hf.space",
        secret="new-token",
        model="space-embedding",
        dimension=1024,
        options={
            key: {
                "api": "embed_batch_text",
                "inputs": ["$texts", task, "$dimension"],
                "output": "0.embeddings",
            }
            for key, task in [("spaces_query", "query"), ("spaces_document", "document")]
        },
    )
    tasks = []

    def handle(request):
        assert request.headers["Authorization"] == "Bearer new-token"
        if request.method == "POST":
            texts, task, dim = json.loads(request.content)["data"]
            assert len(texts) == 1 and dim == 1024
            tasks.append(task)
            return httpx.Response(200, json={"event_id": "abc"})
        return httpx.Response(
            200,
            text="event: complete\ndata: "
            + json.dumps([{"status": "success", "embeddings": [[0.1] * 1024]}])
            + "\n\n",
        )

    provider.client.transport = httpx.MockTransport(handle)
    assert len(await provider.embed_query("question")) == 1024
    assert len((await provider.embed_documents(["document"]))[0]) == 1024
    assert tasks == ["query", "document"]


@pytest.mark.parametrize(
    "url", ["https://huggingface.co/spaces/quyendzvaio/sict", "https://quyendzvaio-sict.hf.space/"]
)
async def test_sict_url_only_autoconfigures_and_discovers_dimension(url):
    connection = ConnectionInput(
        name="SICT",
        provider_type="OPENAI_COMPATIBLE",
        catalog_id="huggingface-spaces",
        base_url=url,
    )
    assert json.loads(connection.config_json["spaces_query"])["inputs"][1] == "query"
    assert json.loads(connection.config_json["spaces_document"])["inputs"][1] == "document"

    def handler(request):
        if request.url.host == "huggingface.co":
            return httpx.Response(200, json={"host": "https://quyendzvaio-sict.hf.space"})
        return httpx.Response(200, json={"named_endpoints": {"/embed_batch_text": {}}})

    models = await discover_models(
        SimpleNamespace(**connection.model_dump()), None, transport=httpx.MockTransport(handler)
    )
    assert models[0].dimension == 1024
    from app.modules.ai_providers.control_service import infer_dimension

    assert (
        await infer_dimension(SimpleNamespace(**connection.model_dump()), "space-embedding", None)
        == 1024
    )


def test_sict_preserves_explicit_mapping():
    from app.modules.ai_providers.space_presets import sict_defaults

    custom = {"spaces_query": json.dumps({"api": "custom", "inputs": ["$text"]})}
    assert sict_defaults("https://quyendzvaio-sict.hf.space", custom) == custom


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "https://evil.com",
        "https://a.hf.space.evil.com",
        "https://a.hf.space/private",
    ],
)
def test_restrict_space_origins(url):
    with pytest.raises(ValueError):
        space_origin(url)


def test_invalid_mapping_and_output_path():
    with pytest.raises(ProviderConfigurationError):
        mapping({"spaces_chat": '{"api":"../private", "inputs":[]}'}, "spaces_chat")
    with pytest.raises(ProviderInvalidResponseError):
        extract([{"text": "value"}], "0.no_such_key")


async def test_inspection_resolves_hub_url_and_forwards_token_only_to_hf():
    seen = []

    def handle(request):
        seen.append(str(request.url))
        assert request.headers["Authorization"] == "Bearer private"
        if request.url.host == "huggingface.co":
            return httpx.Response(200, json={"host": "https://test.hf.space"})
        return httpx.Response(
            200,
            json={
                "named_endpoints": {
                    "/predict": {
                        "parameters": [{"parameter_name": "text"}],
                        "returns": [{"type": "string"}],
                    }
                }
            },
        )

    client = SpaceClient(
        "https://huggingface.co/spaces/owner/test", "private", httpx.MockTransport(handle)
    )
    metadata = await client.inspect()
    assert metadata["endpoints"][0]["name"] == "predict"
    assert seen[-1] == "https://test.hf.space/gradio_api/info"


async def test_queue_ignores_heartbeat_and_extracts_nested_output():
    def handle(request):
        if request.method == "POST":
            assert json.loads(request.content) == {"data": ["hello", 1024]}
            return httpx.Response(200, json={"event_id": "abc"})
        return httpx.Response(
            200, text='event: heartbeat\ndata: null\n\nevent: complete\ndata: [{"answer":"ok"}]\n\n'
        )

    client = SpaceClient("https://test.hf.space", transport=httpx.MockTransport(handle))
    output = await client.call(
        {"api": "predict", "inputs": ["$text", "$dimension"], "output": "0.answer"},
        {"$text": "hello", "$dimension": 1024},
    )
    assert output == "ok"


async def test_queue_auth_error_and_missing_result():
    client = SpaceClient(
        "https://test.hf.space", transport=httpx.MockTransport(lambda _: httpx.Response(401))
    )
    with pytest.raises(ProviderAuthenticationError):
        await client.inspect()
    client.transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"event_id": "abc"})
        if request.method == "POST"
        else httpx.Response(200, text="")
    )
    with pytest.raises(ProviderInvalidResponseError):
        await client.call({"api": "predict", "inputs": []}, {})


async def test_embedding_query_document_mappings_and_dimension():
    provider = SpacesEmbeddingProvider(
        base_url="https://test.hf.space",
        secret=None,
        model="space-embedding",
        dimension=2,
        options={
            key: {"api": api, "inputs": ["$text"], "output": "0"}
            for key, api in [("spaces_query", "query"), ("spaces_document", "document")]
        },
    )
    seen = []

    async def call(spec, variables):
        seen.append((spec["api"], variables["$text"]))
        return [0.1, 0.2]

    provider.client.call = call
    assert await provider.embed_query("question") == [0.1, 0.2]
    assert await provider.embed_documents(["first", "second"]) == [[0.1, 0.2], [0.1, 0.2]]
    assert seen == [("query", "question"), ("document", "first"), ("document", "second")]
    provider.metadata = provider.metadata.__class__("spaces", "model", 3)
    with pytest.raises(ProviderInvalidResponseError):
        await provider.embed_query("wrong dimension")


async def test_chat_preserves_messages_for_structured_mapping():
    provider = SpacesChatProvider(
        base_url="https://test.hf.space",
        secret=None,
        model="space-chat",
        options={"spaces_chat": {"api": "chat", "inputs": ["$messages"], "output": "0"}},
    )

    async def call(spec, variables):
        assert variables["$messages"] == [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "hello"},
        ]
        return "answer"

    provider.client.call = call
    result = [
        delta
        async for delta in provider.stream_chat(
            [ChatMessage("system", "rules"), ChatMessage("user", "hello")], ChatOptions()
        )
    ]
    assert result[0].text == "answer"


async def test_catalog_connection_registry_and_discovery():
    connection = ConnectionInput(
        name="Space",
        provider_type="OPENAI_COMPATIBLE",
        catalog_id="huggingface-spaces",
        base_url="https://test.hf.space",
        config_json={"spaces_chat": json.dumps({"api": "predict", "inputs": ["$prompt"]})},
    )
    provider = ProviderRegistry().create(
        ProviderDescriptor(
            provider_type="OPENAI_COMPATIBLE",
            capability="CHAT",
            base_url=connection.base_url,
            model="space-chat",
            options=connection.config_json,
        ),
        None,
    )
    assert isinstance(provider, SpacesChatProvider)
    models = await discover_models(
        SimpleNamespace(**connection.model_dump()),
        None,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"named_endpoints": {"/predict": {}}})
        ),
    )
    assert [(row.model, row.capabilities) for row in models] == [("space-chat", ["CHAT"])]
