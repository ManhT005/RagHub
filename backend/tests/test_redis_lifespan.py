import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from redis.exceptions import ConnectionError

from app.core import redis as redis_module
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.exceptions import register_exception_handlers
from app.modules.chatbots import router
from app.modules.chatbots.public_limits import ACQUIRE_SCRIPT, RELEASE_SCRIPT, PublicChatLimits


@pytest.fixture
def shared_redis(monkeypatch):
    client = AsyncMock()
    factory = Mock(return_value=client)
    monkeypatch.setattr(redis_module.Redis, "from_url", factory)
    monkeypatch.setattr(redis_module, "get_settings", lambda: Settings())
    return client, factory


@pytest.mark.asyncio
async def test_public_requests_reuse_client_until_shutdown(shared_redis, monkeypatch):
    redis, factory = shared_redis
    bot = SimpleNamespace(id=uuid4(), organization_id=uuid4())

    class Service:
        def __init__(self, session):
            pass

        async def public_chatbot(self, *args):
            return bot

        async def stream(self, *args):
            yield "done", {}

    monkeypatch.setattr(router, "ChatbotService", Service)
    app = FastAPI(lifespan=redis_module.redis_lifespan)
    register_exception_handlers(app)
    app.include_router(router.router)
    app.dependency_overrides[get_session] = lambda: None
    app.dependency_overrides[get_settings] = lambda: Settings()
    redis.eval.side_effect = lambda script, *args: 1 if script == ACQUIRE_SCRIPT else 0

    async with app.router.lifespan_context(app):
        assert app.state.redis is redis
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(3):
                result = await client.post("/public/chatbots/rgh_test/chat", json={"message": "Hi"})
                assert result.status_code == 200
                assert "event: done" in result.text
            releases = [
                call for call in redis.eval.await_args_list if call.args[0] == RELEASE_SCRIPT
            ]
            assert len(releases) == 3
            assert len({call.args[-1] for call in releases}) == 3
            redis.eval.return_value = 10
            redis.eval.side_effect = None
            result = await client.post("/public/chatbots/rgh_test/chat", json={"message": "Hi"})
            assert result.status_code == 429
            redis.eval.side_effect = ConnectionError("unavailable")
            result = await client.post("/public/chatbots/rgh_test/chat", json={"message": "Hi"})
            assert result.status_code == 503
        factory.assert_called_once()
        redis.aclose.assert_not_awaited()
    redis.aclose.assert_awaited_once()
    assert not hasattr(app.state, "redis")


@pytest.mark.asyncio
@pytest.mark.parametrize("release_fails", [False, True])
async def test_disconnected_stream_does_not_close_client_or_release_other_lease(
    shared_redis, release_fails
):
    redis, factory = shared_redis
    app = FastAPI(lifespan=redis_module.redis_lifespan)
    first_entered = asyncio.Event()
    second_entered = asyncio.Event()
    finish_second = asyncio.Event()

    async def first_body():
        first_entered.set()
        await asyncio.Event().wait()
        yield "unreachable"

    async def second_body():
        second_entered.set()
        await finish_second.wait()
        yield "event: done\ndata: {}\n\n"

    async def disconnect():
        await first_entered.wait()
        await second_entered.wait()
        return {"type": "http.disconnect"}

    async def stay_connected():
        await asyncio.Event().wait()

    async with app.router.lifespan_context(app):
        limits = PublicChatLimits(app.state.redis, Settings())
        redis.eval.return_value = 1
        first_token = await limits.acquire("bot")
        second_token = await limits.acquire("bot")
        assert first_token != second_token

        async def evaluate(script, *args):
            if release_fails and script == RELEASE_SCRIPT and args[-1] == first_token:
                raise ConnectionError("release failed")
            return 1

        redis.eval.side_effect = evaluate
        scope = {"type": "http", "asgi": {"spec_version": "2.0"}}
        first = router.PublicStreamingResponse(
            first_body(), limits=limits, chatbot_id="bot", slot=first_token
        )
        second = router.PublicStreamingResponse(
            second_body(), limits=limits, chatbot_id="bot", slot=second_token
        )
        first_task = asyncio.create_task(first(scope, disconnect, AsyncMock()))
        second_task = asyncio.create_task(second(scope, stay_connected, AsyncMock()))
        try:
            await asyncio.wait_for(asyncio.shield(first_task), timeout=2)
            assert not second_task.done()
            releases = [
                call.args[-1]
                for call in redis.eval.await_args_list
                if call.args[0] == RELEASE_SCRIPT
            ]
            assert releases == [first_token]
            redis.aclose.assert_not_awaited()
            finish_second.set()
            await asyncio.wait_for(asyncio.shield(second_task), timeout=2)
            releases = [
                call.args[-1]
                for call in redis.eval.await_args_list
                if call.args[0] == RELEASE_SCRIPT
            ]
            assert releases == [first_token, second_token]
            redis.aclose.assert_not_awaited()
        finally:
            for task in (first_task, second_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(first_task, second_task, return_exceptions=True)
    factory.assert_called_once()
    redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_client_closes_when_lifespan_exits_with_error(shared_redis):
    redis, _ = shared_redis
    app = FastAPI(lifespan=redis_module.redis_lifespan)
    with pytest.raises(RuntimeError, match="application failed"):
        async with app.router.lifespan_context(app):
            raise RuntimeError("application failed")
    redis.aclose.assert_awaited_once()
    assert not hasattr(app.state, "redis")
