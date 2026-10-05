"""Exercise the actual Lua scripts against Redis, including simultaneous admissions."""

import asyncio
import os
from uuid import uuid4

import pytest
from raghub_core.domain.errors import CoreError
from redis.asyncio import Redis

from app.core.config import Settings
from app.delivery.http.error_mapping import http_status
from app.infrastructure.redis.public_chat_admission import PublicChatLimits

pytestmark = pytest.mark.integration


async def test_atomic_rate_and_slot_leases():
    url = os.getenv("RAGHUB_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set RAGHUB_TEST_REDIS_URL to run real Redis admission tests.")
    namespace = "test:" + uuid4().hex + ":"
    async with Redis.from_url(url) as redis:

        class NamespacedRedis:
            async def eval(self, script, count, *args):
                keys = [namespace + key for key in args[:count]]
                return await redis.eval(script, count, *keys, *args[count:])

        settings = Settings(
            _env_file=None,
            public_chat_requests_per_ip=3,
            public_chat_requests_per_chatbot=5,
            public_chat_concurrent_global=3,
            public_chat_concurrent_per_chatbot=2,
        )
        limits = PublicChatLimits(NamespacedRedis(), settings)
        try:
            results = await asyncio.gather(
                *(limits.check_rate("bot", "ip") for _ in range(20)), return_exceptions=True
            )
            assert sum(result is None for result in results) == 3
            rejected = [result for result in results if isinstance(result, CoreError)]
            assert len(rejected) == 17 and all(http_status(result) == 429 for result in rejected)
            await limits.check_rate("bot", "other-ip")
            await limits.check_rate("bot", "third-ip")
            with pytest.raises(CoreError):
                await limits.check_rate("bot", "fourth-ip")
            results = await asyncio.gather(
                *(limits.acquire("bot") for _ in range(20)), return_exceptions=True
            )
            tokens = [result for result in results if isinstance(result, str)]
            assert len(tokens) == 2
            other_token = await limits.acquire("other-bot")
            with pytest.raises(CoreError):
                await limits.acquire("third-bot")
            await limits.release("bot", tokens[0])
            # Duplicate cleanup cannot release someone else's slot.
            await limits.release("bot", tokens[0])
            assert await redis.zcard(namespace + "public:active:global") == 2
            replacement = await limits.acquire("bot")
            assert replacement not in tokens
            await limits.release("bot", tokens[1])
            await limits.release("bot", replacement)
            await limits.release("other-bot", other_token)
            # Simulate a crashed worker's expired lease using Redis server time.
            token = await limits.acquire("bot")
            for key in limits.slot_keys("bot"):
                await redis.zadd(namespace + key, {token: 0})
            assert await limits.acquire("bot")
            # Rate window expiry admits traffic again.
            async for key in redis.scan_iter(match=namespace + "public:rate:*"):
                await redis.pexpire(key, 1)
            await asyncio.sleep(0.02)
            await limits.check_rate("bot", "ip")
        finally:
            keys = [key async for key in redis.scan_iter(match=namespace + "*")]
            if keys:
                await redis.delete(*keys)
