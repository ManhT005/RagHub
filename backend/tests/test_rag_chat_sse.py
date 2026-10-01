from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.modules.ai_providers.errors import ProviderUnavailableError
from app.modules.chatbots.provider import GeminiChatProvider
from app.modules.chatbots.router import chat
from app.modules.chatbots.schemas import ChatRequest


@pytest.mark.asyncio
async def test_chat_sse_emits_contract_events(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeService:
        def __init__(self, session: object) -> None:
            self.session = session

        async def stream(self, *args: object):
            yield "conversation", {"conversation_id": "conversation"}
            yield "citations", {"citations": [{"chunk_id": "chunk"}]}
            yield "token", {"text": "Xin chào"}
            yield "usage", {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}
            yield "done", {"message_id": "message", "first_token_ms": 1, "latency_ms": 1}

    import app.modules.chatbots.router as chat_router

    monkeypatch.setattr(chat_router, "ChatbotService", FakeService)
    response = await chat(
        uuid4(),
        ChatRequest(message="Xin chào"),
        SimpleNamespace(organization_id=uuid4()),
        SimpleNamespace(id=uuid4()),
        object(),
    )
    body = "".join([chunk async for chunk in response.body_iterator])
    assert response.media_type == "text/event-stream"
    positions = [
        body.index(f"event: {event}")
        for event in ("conversation", "citations", "token", "usage", "done")
    ]
    assert positions == sorted(positions)


@pytest.mark.asyncio
async def test_chat_sse_converts_service_error_to_event(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeService:
        def __init__(self, session: object) -> None:
            self.session = session

        async def stream(self, *args: object):
            raise AppError("CHAT_PROVIDER_TIMEOUT", "Gemini timed out.", status_code=504)
            yield  # pragma: no cover

    import app.modules.chatbots.router as chat_router

    monkeypatch.setattr(chat_router, "ChatbotService", FakeService)
    response = await chat(
        uuid4(),
        ChatRequest(message="Xin chào"),
        SimpleNamespace(organization_id=uuid4()),
        SimpleNamespace(id=uuid4()),
        object(),
    )
    body = "".join([chunk async for chunk in response.body_iterator])
    assert "event: error" in body
    assert "CHAT_PROVIDER_TIMEOUT" in body


@pytest.mark.asyncio
async def test_stream_error_after_token_does_not_emit_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeService:
        def __init__(self, session: object) -> None:
            self.session = session

        async def stream(self, *args: object):
            yield "conversation", {"conversation_id": "conversation"}
            yield "citations", {"citations": []}
            yield "token", {"text": "partial"}
            raise ProviderUnavailableError()

    import app.modules.chatbots.router as chat_router

    monkeypatch.setattr(chat_router, "ChatbotService", FakeService)
    response = await chat(
        uuid4(),
        ChatRequest(message="Xin chĂ o"),
        SimpleNamespace(organization_id=uuid4()),
        SimpleNamespace(id=uuid4()),
        object(),
    )

    body = "".join([chunk async for chunk in response.body_iterator])

    assert body.count("event: token") == 1
    assert body.index("event: token") < body.index("event: error")
    assert "PROVIDER_UNAVAILABLE" in body
    assert "event: done" not in body


@pytest.mark.asyncio
async def test_gemini_provider_requires_server_side_key() -> None:
    from app.core.config import Settings

    provider = GeminiChatProvider(Settings(gemini_api_key=""))
    with pytest.raises(AppError, match="Gemini is not configured"):
        async for _ in provider.stream_chat(messages=[], model="gemini-2.5-flash"):
            pass
