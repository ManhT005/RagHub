from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from redis.exceptions import ConnectionError

from app.core.config import Settings
from app.core.database import get_session
from app.core.exceptions import AppError, register_exception_handlers
from app.modules.chatbots import router
from app.modules.chatbots.public_limits import PublicChatLimits, get_public_limits


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
    assert error.value.status_code == 429
    assert error.value.details == {"retry_after_seconds": 23}


@pytest.mark.asyncio
async def test_redis_failure_fails_closed():
    redis = AsyncMock()
    redis.eval.side_effect = ConnectionError()
    with pytest.raises(AppError) as error:
        await PublicChatLimits(redis, Settings()).check_rate("bot", "ip")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_http_rate_limit_and_admin_isolation(monkeypatch):
    bot = SimpleNamespace(id=uuid4(), organization_id=uuid4())

    class Service:
        def __init__(self, session):
            pass

        async def public_chatbot(self, *args):
            return bot

        async def stream(self, *args):
            yield "done", {}

    monkeypatch.setattr(router, "ChatbotService", Service)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router.router)
    app.dependency_overrides[get_session] = lambda: None
    limits = AsyncMock()
    app.dependency_overrides[get_public_limits] = lambda: limits
    app.dependency_overrides[router.get_organization_context] = lambda: bot
    app.dependency_overrides[router.get_current_user] = lambda: bot
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        headers = {"Origin": "https://example.com"}
        result = await client.post(
            "/public/chatbots/rgh_test/chat", json={"message": "Hi"}, headers=headers,
        )
        assert result.status_code == 200
        assert "event: done" in result.text
        limits.check_rate.side_effect = AppError(
            "PUBLIC_CHAT_RATE_LIMITED", "Too many requests.", status_code=429,
            details={"retry_after_seconds": 12},
        )
        result = await client.post(
            "/public/chatbots/rgh_test/chat", json={"message": "Hi"}, headers=headers,
        )
        assert result.status_code == 429
        assert result.headers["retry-after"] == "12"
        assert result.headers["access-control-allow-origin"] == headers["Origin"]
        result = await client.post(f"/chatbots/{bot.id}/chat", json={"message": "Hi"})
        assert result.status_code == 200
        assert limits.check_rate.await_count == 2
