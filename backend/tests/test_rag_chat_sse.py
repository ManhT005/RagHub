from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
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
            yield "done", {"message_id": "message", "latency_ms": 1}

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
    assert [
        f"event: {event}" in body for event in ("conversation", "citations", "token", "done")
    ] == [
        True,
        True,
        True,
        True,
    ]


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
async def test_gemini_provider_requires_server_side_key() -> None:
    from app.core.config import Settings

    provider = GeminiChatProvider(Settings(gemini_api_key=""))
    with pytest.raises(AppError, match="Gemini is not configured"):
        async for _ in provider.stream_chat(messages=[], model="gemini-2.5-flash"):
            pass
