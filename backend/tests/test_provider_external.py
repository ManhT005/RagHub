import httpx
import pytest

from app.modules.ai_providers.adapters.openai_compatible import (
    OpenAICompatibleChatProvider,
    OpenAICompatibleEmbeddingProvider,
)
from app.modules.ai_providers.contracts import ChatMessage, ChatOptions
from app.modules.ai_providers.errors import (
    ProviderInvalidResponseError,
    ProviderUnavailableError,
)
from app.modules.ai_providers.policy import ProviderRequestPolicy


class FakeClient:
    response: httpx.Response

    def __init__(self, **_kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    async def post(self, *args: object, **kwargs: object) -> httpx.Response:
        return self.response


@pytest.mark.asyncio
async def test_openai_embedding_normalizes_order_and_validates_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeClient.response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://provider.test/embeddings"),
        json={
            "data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]
        },
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://provider.test",
        model="embedding-model",
        dimension=2,
        secret="test-secret",
        policy=ProviderRequestPolicy(max_attempts=1),
    )

    assert await provider.embed_documents(["first", "second"]) == [
        [1.0, 0.0],
        [0.0, 1.0],
    ]


@pytest.mark.asyncio
async def test_openai_embedding_rejects_dimension_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeClient.response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://provider.test/embeddings"),
        json={"data": [{"index": 0, "embedding": [1.0]}]},
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://provider.test",
        model="embedding-model",
        dimension=2,
        secret=None,
        policy=ProviderRequestPolicy(max_attempts=1),
    )

    with pytest.raises(ProviderInvalidResponseError):
        await provider.embed_query("query")


@pytest.mark.asyncio
async def test_openai_embedding_retries_bounded_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        httpx.Response(503, request=httpx.Request("POST", "https://provider.test/embeddings")),
        httpx.Response(
            200,
            request=httpx.Request("POST", "https://provider.test/embeddings"),
            json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]},
        ),
    ]
    calls = 0

    class SequenceClient(FakeClient):
        async def post(self, *args: object, **kwargs: object) -> httpx.Response:
            nonlocal calls
            response = responses[calls]
            calls += 1
            return response

    monkeypatch.setattr(httpx, "AsyncClient", SequenceClient)
    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://provider.test",
        model="embedding-model",
        dimension=2,
        secret=None,
        policy=ProviderRequestPolicy(max_attempts=2, backoff_seconds=0),
    )

    assert await provider.embed_query("query") == [1.0, 0.0]
    assert calls == 2


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_first_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    class StreamingResponse:
        status_code = 200

        async def aiter_lines(self):  # type: ignore[no-untyped-def]
            yield 'data: {"choices":[{"delta":{"content":"first"}}]}'
            raise httpx.ReadError(
                "connection lost", request=httpx.Request("POST", "https://provider.test")
            )

    class StreamContext:
        async def __aenter__(self) -> StreamingResponse:
            return StreamingResponse()

        async def __aexit__(self, *_args: object) -> None:
            pass

    class StreamingClient(FakeClient):
        def stream(self, *args: object, **kwargs: object) -> StreamContext:
            nonlocal calls
            calls += 1
            return StreamContext()

    monkeypatch.setattr(httpx, "AsyncClient", StreamingClient)
    provider = OpenAICompatibleChatProvider(
        base_url="https://provider.test",
        model="chat-model",
        secret=None,
        policy=ProviderRequestPolicy(max_attempts=3, backoff_seconds=0),
    )
    tokens: list[str] = []

    with pytest.raises(ProviderUnavailableError):
        async for token in provider.stream_chat([ChatMessage("user", "hello")], ChatOptions()):
            tokens.append(token)

    assert tokens == ["first"]
    assert calls == 1
