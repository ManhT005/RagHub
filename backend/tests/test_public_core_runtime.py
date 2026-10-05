import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from starlette.requests import Request

import app.modules.chatbots.router as router
from app.core.config import Settings
from app.delivery.security.origins import origin_is_allowed
from app.modules.chatbots.schemas import ChatRequest, EmbedPublishInput
from raghub_core.domain.rag.events import ChatCompleted, ChatFailed, TokenDelta
from raghub_core.domain.rag.models import StreamChatCommand


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.com",
        "https://example.com/path",
        "https://user@example.com",
        "https://example.com?query=x",
        "https://example.com#fragment",
        "file://example.com",
    ],
)
def test_public_origin_configuration_rejects_non_origins(origin):
    with pytest.raises(ValidationError):
        EmbedPublishInput(allowed_origins=[origin])
    assert not origin_is_allowed(origin, [origin])


def test_public_origin_matches_scheme_host_and_port_without_wildcards():
    policy = EmbedPublishInput(
        allowed_origins=["HTTPS://Example.COM:443/", "http://localhost:8081"]
    )
    assert policy.allowed_origins == ["https://example.com", "http://localhost:8081"]
    assert origin_is_allowed("https://example.com", policy.allowed_origins)
    assert not origin_is_allowed("http://example.com", policy.allowed_origins)
    assert not origin_is_allowed("https://example.com:8443", policy.allowed_origins)
    assert not origin_is_allowed("https://evil.example.com", policy.allowed_origins)
    assert not origin_is_allowed("null", ["*"])


@pytest.mark.parametrize(
    "outcome", ["done", "provider_error", "timeout", "disconnect", "serialization"]
)
async def test_public_delivery_uses_server_scope_and_closes_typed_runtime_on_every_exit(
    monkeypatch, outcome
):
    bot = SimpleNamespace(id=uuid4(), organization_id=uuid4(), workspace_id=uuid4())
    entered, closed, commands = asyncio.Event(), [], []

    class Service:
        def __init__(self, session):
            pass

        async def resolve(self, key, origin):
            assert key == "rgh_test" and origin == "https://example.com"
            return bot

        async def stream_events(self, command):
            commands.append(command)
            entered.set()
            try:
                if outcome in {"timeout", "disconnect"}:
                    await asyncio.sleep(10)
                if outcome == "serialization":
                    yield TokenDelta(object())
                elif outcome == "provider_error":
                    yield ChatFailed("PROVIDER_UNAVAILABLE", "The AI provider is unavailable.")
                else:
                    yield ChatCompleted(uuid4(), None, 0)
            finally:
                closed.append(True)

    monkeypatch.setattr(router, "PublicChatContainer", Service)
    limits = AsyncMock()
    limits.settings = Settings(_env_file=None, public_chat_stream_timeout_seconds=1)
    request = Request({"type": "http", "client": ("127.0.0.1", 1234)})
    payload = ChatRequest.model_validate(
        {
            "message": "question",
            "organization_id": str(uuid4()),
            "workspace_id": str(uuid4()),
        }
    )
    response = await router.public_chat(
        "rgh_test", payload, request, "https://example.com", None, limits
    )
    frames = []

    async def receive():
        await entered.wait()
        if outcome != "disconnect":
            await asyncio.sleep(10)
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body":
            frames.append(message["body"].decode())

    try:
        await response({"type": "http", "asgi": {"spec_version": "2.0"}}, receive, send)
    except Exception:
        assert outcome == "serialization"
    assert commands == [StreamChatCommand(bot.organization_id, bot.id, "question")]
    assert closed == [True]
    limits.release.assert_awaited_once_with(str(bot.id), limits.acquire.return_value)
    limits.check_rate.assert_awaited_once()
    if outcome == "provider_error":
        assert request.state.public_error_code == "PROVIDER_UNAVAILABLE"
        assert "event: error" in "".join(frames)
    if outcome == "timeout":
        assert request.state.public_error_code == "PUBLIC_CHAT_TIMEOUT"
        assert "PUBLIC_CHAT_TIMEOUT" in "".join(frames)
