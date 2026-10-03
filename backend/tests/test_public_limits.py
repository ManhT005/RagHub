from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from redis.exceptions import ConnectionError

from app.core.config import Settings
from app.core.database import get_session
from app.core.exceptions import register_exception_handlers
from app.core_domain.errors import CoreError as AppError
from app.delivery.http.error_mapping import http_status
from app.modules.chatbots import router
from app.modules.chatbots.public_limits import PublicChatLimits, get_public_limits


@pytest.mark.asyncio
async def test_concurrent_admission_and_unique_release():
    redis = AsyncMock()
    redis.eval.return_value = 1
    limits = PublicChatLimits(redis, Settings())
    token = await limits.acquire("bot")
    assert redis.eval.call_args.args[2:7] == (
        "public:active:global",
        "public:active:bot:bot",
        32,
        4,
        100,
    )
    await limits.release("bot", token)
    assert redis.eval.call_args.args[-1] == token
    redis.eval.return_value = 0
    with pytest.raises(AppError) as error:
        await limits.acquire("bot")
    assert http_status(error.value) == 429
    assert error.value.code == "PUBLIC_CHAT_CONCURRENCY_LIMITED"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["done", "provider_error", "timeout", "disconnect"])
async def test_stream_releases_slot_on_every_exit(outcome):
    import asyncio

    from app.modules.chatbots.router import PublicStreamingResponse

    limits = AsyncMock()
    entered = asyncio.Event()
    limits.settings = Settings()
    limits.redis = AsyncMock()

    async def body():
        entered.set()
        if outcome == "provider_error":
            raise RuntimeError("provider failed")
        if outcome == "timeout":
            async with asyncio.timeout(0.01):
                await asyncio.sleep(10)
        if outcome == "disconnect":
            await asyncio.sleep(10)
        yield "event: done\ndata: {}\n\n"

    async def receive():
        await entered.wait()
        if outcome != "disconnect":
            await asyncio.sleep(10)
        return {"type": "http.disconnect"}

    response = PublicStreamingResponse(body(), limits=limits, chatbot_id="bot", slot="slot")
    try:
        await response({"type": "http", "asgi": {"spec_version": "2.0"}}, receive, AsyncMock())
    except Exception:
        assert outcome in {"provider_error", "timeout"}
    limits.release.assert_awaited_once_with("bot", "slot")
    limits.redis.aclose.assert_not_awaited()


@pytest.mark.asyncio
async def test_rate_keys_are_shared_and_do_not_contain_raw_ip():
    redis = AsyncMock()
    redis.eval.return_value = 0
    limits = PublicChatLimits(redis, Settings())
    await limits.check_rate("bot-id", "192.0.2.1")
    args = redis.eval.call_args.args
    assert args[1] == 2
    assert "192.0.2.1" not in args[2]
    assert args[3:] == ("public:rate:bot:bot-id", 20, 120)
    redis.eval.return_value = 23
    with pytest.raises(AppError) as error:
        await limits.check_rate("bot-id", "192.0.2.1")
    assert http_status(error.value) == 429
    assert error.value.details == {"retry_after_seconds": 23}


@pytest.mark.asyncio
async def test_redis_failure_fails_closed():
    redis = AsyncMock()
    redis.eval.side_effect = ConnectionError()
    with pytest.raises(AppError) as error:
        await PublicChatLimits(redis, Settings()).check_rate("bot", "ip")
    assert http_status(error.value) == 503


@pytest.mark.asyncio
async def test_http_rate_limit_and_admin_isolation(monkeypatch):
    bot = SimpleNamespace(id=uuid4(), organization_id=uuid4(), workspace_id=uuid4())

    class Service:
        def __init__(self, session):
            pass

        async def resolve(self, *args):
            return bot

        async def get(self, *args):
            return bot

        async def stream(self, *args):
            yield "done", {}

        async def stream_events(self, *args):
            from app.core_domain.rag.events import ChatCompleted

            yield ChatCompleted(uuid4(), None, 0)

    monkeypatch.setattr(router, "PublicChatContainer", Service)
    monkeypatch.setattr(router, "ChatbotService", Service)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router.router)
    app.dependency_overrides[get_session] = lambda: None
    limits = AsyncMock()
    limits.settings = Settings()
    app.dependency_overrides[get_public_limits] = lambda: limits
    app.dependency_overrides[router.get_organization_context] = lambda: SimpleNamespace(
        organization_id=bot.organization_id,
        membership=SimpleNamespace(role="ADMIN"),
    )
    app.dependency_overrides[router.get_current_user] = lambda: bot
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        headers = {"Origin": "https://example.com"}
        result = await client.post(
            "/public/chatbots/rgh_test/chat",
            json={"message": "Hi"},
            headers=headers,
        )
        assert result.status_code == 200
        assert "event: done" in result.text
        assert limits.release.await_count == 1
        limits.check_rate.side_effect = AppError(
            "PUBLIC_CHAT_RATE_LIMITED",
            "Too many requests.",
            details={"retry_after_seconds": 12},
        )
        result = await client.post(
            "/public/chatbots/rgh_test/chat",
            json={"message": "Hi"},
            headers=headers,
        )
        assert result.status_code == 429
        assert result.headers["retry-after"] == "12"
        assert result.headers["access-control-allow-origin"] == headers["Origin"]
        result = await client.post(f"/chatbots/{bot.id}/chat", json={"message": "Hi"})
        assert result.status_code == 200
        assert limits.check_rate.await_count == 2
