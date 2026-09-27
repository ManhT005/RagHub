import json

import httpx
import pytest

from app.modules.ai_providers.adapters.ollama import OllamaChatProvider
from app.modules.ai_providers.adapters.openai_compatible import OpenAICompatibleChatProvider
from app.modules.ai_providers.contracts import ChatMessage, ChatOptions
from app.modules.ai_providers.policy import ProviderRequestPolicy


class StreamContext:
    def __init__(self, response: object) -> None:
        self.response = response

    async def __aenter__(self) -> object:
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        pass


class Client:
    response: object
    payload: dict[str, object]

    def __init__(self, **_kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "Client":
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    def stream(self, *_args: object, **kwargs: object) -> StreamContext:
        Client.payload = kwargs["json"]
        return StreamContext(self.response)


@pytest.mark.asyncio
async def test_openai_stream_collects_provider_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200

        async def aiter_lines(self):  # type: ignore[no-untyped-def]
            yield 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
            yield (
                'data: {"choices":[],"usage":{"prompt_tokens":8,'
                '"completion_tokens":1,"total_tokens":9}}'
            )
            yield "data: [DONE]"

    Client.response = Response()
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    provider = OpenAICompatibleChatProvider(
        base_url="https://provider.test",
        model="model",
        secret=None,
        policy=ProviderRequestPolicy(max_attempts=1),
    )

    deltas = [
        delta
        async for delta in provider.stream_chat([ChatMessage("user", "Hi")], ChatOptions())
    ]

    assert Client.payload["stream_options"] == {"include_usage": True}
    assert [delta.text for delta in deltas if delta.text] == ["Hello"]
    assert next(delta.usage for delta in deltas if delta.usage).total_tokens == 9
    assert next(delta.usage for delta in deltas if delta.usage).source == "provider"


@pytest.mark.asyncio
async def test_ollama_stream_maps_native_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200

        async def aiter_lines(self):  # type: ignore[no-untyped-def]
            yield json.dumps({"message": {"content": "Hello"}, "done": False})
            yield json.dumps(
                {
                    "message": {"content": ""},
                    "done": True,
                    "prompt_eval_count": 7,
                    "eval_count": 2,
                }
            )

    Client.response = Response()
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    provider = OllamaChatProvider(
        base_url="http://ollama:11434",
        model="model",
        policy=ProviderRequestPolicy(max_attempts=1),
    )

    deltas = [
        delta
        async for delta in provider.stream_chat([ChatMessage("user", "Hi")], ChatOptions())
    ]

    usage = next(delta.usage for delta in deltas if delta.usage)
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (7, 2, 9)
    assert usage.source == "provider"


@pytest.mark.asyncio
async def test_openai_stream_estimates_usage_when_provider_omits_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 200

        async def aiter_lines(self):  # type: ignore[no-untyped-def]
            yield 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
            yield "data: [DONE]"

    Client.response = Response()
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    provider = OpenAICompatibleChatProvider(
        base_url="https://provider.test",
        model="model",
        secret=None,
        policy=ProviderRequestPolicy(max_attempts=1),
    )

    deltas = [
        delta
        async for delta in provider.stream_chat([ChatMessage("user", "Hi")], ChatOptions())
    ]

    usage = next(delta.usage for delta in deltas if delta.usage)
    assert usage.total_tokens > 0
    assert usage.source == "estimated"
