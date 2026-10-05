import json
import math
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from app.infrastructure.persistence.provider_descriptors import provider_descriptor
from app.modules.ai_providers.adapters.sentence_transformer import SentenceTransformerModelRegistry
from app.modules.ai_providers.models import EmbeddingIndexVersion, ProviderConfig
from app.modules.ai_providers.registry import ProviderRegistry
from raghub_core.domain.providers.contracts import (
    ChatMessage,
    ChatOptions,
    ChatProvider,
    EmbeddingProvider,
)
from raghub_core.domain.providers.descriptor import ProviderDescriptor
from raghub_core.domain.providers.errors import (
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

EXTERNAL_EMBEDDING = ["OPENAI_COMPATIBLE", "GOOGLE_GEMINI"]
EMBEDDING_TYPES = [*EXTERNAL_EMBEDDING, "LOCAL_SENTENCE_TRANSFORMER", "LOCAL_TOKEN_HASH"]
CHAT_TYPES = ["OPENAI_COMPATIBLE", "GOOGLE_GEMINI", "OLLAMA"]


class Model:
    async_error = None
    vectors = None

    def encode(self, texts, **_):
        return self.vectors if self.vectors is not None else [[1.0, 0.0] for _ in texts]


class Response:
    status_code = 200

    def __init__(self, client, ollama=False):
        self.client, self.ollama = client, ollama
        self.status_code = client.status

    async def aiter_lines(self):
        if self.ollama:
            yield json.dumps({"message": {"content": "answer"}})
        else:
            yield 'data: {"choices":[{"delta":{"content":"answer"}}]}'
        if self.client.after_token:
            raise httpx.ReadError("stream interrupted")
        if self.ollama:
            yield json.dumps({"done": True, "prompt_eval_count": 3, "eval_count": 2})
        else:
            yield (
                'data: {"choices":[],"usage":{"prompt_tokens":3,'
                '"completion_tokens":2,"total_tokens":5}}'
            )
            yield "data: [DONE]"


class StreamContext:
    def __init__(self, client, ollama):
        self.client, self.ollama = client, ollama

    async def __aenter__(self):
        if self.client.timeout:
            raise httpx.ReadTimeout("private provider error")
        return Response(self.client, self.ollama)

    async def __aexit__(self, *_):
        pass


class Client:
    calls = 0
    status = 200
    timeout = False
    after_token = False
    vectors = None

    def __init__(self, **_):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def post(self, url, **kwargs):
        type(self).calls += 1
        if self.timeout:
            raise httpx.ReadTimeout("private provider error")
        texts = kwargs["json"]["input"]
        vectors = self.vectors if self.vectors is not None else [[1.0, 0.0] for _ in texts]
        return httpx.Response(
            self.status,
            request=httpx.Request("POST", url),
            json={
                "data": [
                    {"index": index, "embedding": vector} for index, vector in enumerate(vectors)
                ],
            },
        )

    def stream(self, method, url, **kwargs):
        type(self).calls += 1
        return StreamContext(self, url.endswith("/api/chat"))


@pytest.fixture
def adapters(monkeypatch):
    class TestClient(Client):
        pass

    model = Model()
    monkeypatch.setattr(httpx, "AsyncClient", TestClient)
    monkeypatch.setattr(SentenceTransformerModelRegistry, "get", lambda _: model)
    return TestClient, model


def create(provider_type, capability, *, attempts=1):
    return ProviderRegistry().create(
        ProviderDescriptor(
            provider_type,
            capability,
            "model",
            "https://provider.test",
            2,
            {"max_attempts": attempts, "backoff_seconds": 0},
        ),
        "test-secret-never-log",
    )


@pytest.mark.parametrize("provider_type", EMBEDDING_TYPES)
async def test_shared_embedding_batch_query_dimension_and_finite_contract(provider_type, adapters):
    provider = create(provider_type, "EMBEDDING")
    assert isinstance(provider, EmbeddingProvider)
    assert await provider.embed_documents([]) == []
    vectors = await provider.embed_documents(["first", "second", "third"])
    assert len(vectors) == 3
    assert all(len(vector) == 2 and all(math.isfinite(x) for x in vector) for vector in vectors)
    query = await provider.embed_query("query")
    assert len(query) == provider.metadata.dimension == 2 and all(map(math.isfinite, query))


@pytest.mark.parametrize("provider_type", [*EXTERNAL_EMBEDDING, "LOCAL_SENTENCE_TRANSFORMER"])
@pytest.mark.parametrize("vectors", [[], [[1.0]], [[float("inf"), 0.0]]])
async def test_shared_embedding_rejects_invalid_vectors(provider_type, vectors, adapters):
    client, model = adapters
    client.vectors = model.vectors = vectors
    with pytest.raises(ProviderInvalidResponseError):
        await create(provider_type, "EMBEDDING").embed_query("query")


@pytest.mark.parametrize("provider_type", CHAT_TYPES)
async def test_shared_chat_stream_and_native_usage_contract(provider_type, adapters):
    provider = create(provider_type, "CHAT")
    assert isinstance(provider, ChatProvider)
    deltas = [
        delta
        async for delta in provider.stream_chat([ChatMessage("user", "question")], ChatOptions())
    ]
    assert [delta.text for delta in deltas if delta.text] == ["answer"]
    usage = next(delta.usage for delta in deltas if delta.usage)
    assert usage.total_tokens == 5 and usage.source == "provider"


@pytest.mark.parametrize("provider_type", CHAT_TYPES)
async def test_shared_chat_does_not_retry_after_first_token(provider_type, adapters):
    client, _ = adapters
    client.after_token = True
    tokens = []
    with pytest.raises(ProviderUnavailableError):
        async for delta in create(provider_type, "CHAT", attempts=3).stream_chat(
            [ChatMessage("user", "question")],
            ChatOptions(),
        ):
            if delta.text:
                tokens.append(delta.text)
    assert tokens == ["answer"] and client.calls == 1


@pytest.mark.parametrize(
    "provider_type,capability",
    [
        *[(provider, "CHAT") for provider in CHAT_TYPES],
        *[(provider, "EMBEDDING") for provider in EXTERNAL_EMBEDDING],
    ],
)
@pytest.mark.parametrize("timed_out", [True, False])
async def test_shared_timeout_rate_limit_and_secret_safety(
    provider_type, capability, timed_out, adapters, caplog
):
    client, _ = adapters
    client.timeout, client.status = timed_out, 429
    provider = create(provider_type, capability)
    with pytest.raises(ProviderTimeoutError if timed_out else ProviderRateLimitError) as error:
        if capability == "CHAT":
            _ = [
                delta
                async for delta in provider.stream_chat([ChatMessage("user", "q")], ChatOptions())
            ]
        else:
            await provider.embed_query("q")
    assert "test-secret-never-log" not in str(error.value) + caplog.text


def test_provider_descriptor_uses_embedding_snapshot_and_excludes_secret():
    config = ProviderConfig(
        provider_type="OPENAI_COMPATIBLE",
        capability="EMBEDDING",
        model="new",
        dimension=3,
        config_json={"new": True},
        encrypted_secret="ciphertext",
    )
    version = EmbeddingIndexVersion(
        provider_type="GOOGLE_GEMINI",
        model="snapshot",
        dimension=2,
        base_url="https://snapshot.test",
        config_json={"snapshot": True},
    )
    descriptor = provider_descriptor(config, version)
    assert descriptor.model == "snapshot" and descriptor.dimension == 2
    assert descriptor.options_dict() == {"snapshot": True}
    assert "ciphertext" not in repr(descriptor) and descriptor.provider_type == "GOOGLE_GEMINI"


def test_registry_imports_without_orm_or_runtime_settings():
    script = """
import importlib.abc
import sys
class BlockOrm(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'sqlalchemy', 'fastapi', 'pydantic_settings'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, BlockOrm())
from app.modules.ai_providers.registry import ProviderRegistry
from raghub_core.domain.providers.descriptor import ProviderDescriptor
descriptor = ProviderDescriptor('LOCAL_TOKEN_HASH', 'EMBEDDING', 'model', dimension=2)
provider = ProviderRegistry().create(descriptor, None)
assert provider.metadata.dimension == 2
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
