import os
import time
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.core.exceptions import AppError
from app.modules.public_chat.concurrency import ConcurrencyLimiter
from app.modules.public_chat.rate_limit import FixedWindowRateLimiter, rate_limit_key

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RAGHUB_RUN_INTEGRATION") != "1",
        reason="Set RAGHUB_RUN_INTEGRATION=1 to run Redis integration tests.",
    ),
]


async def test_real_redis_rate_limit_and_concurrency_lease() -> None:
    redis = Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True
    )
    chatbot_id, organization_id = uuid4(), uuid4()
    ip = f"198.51.100.{int(time.time()) % 200 + 1}"
    rate_key = rate_limit_key("integration", chatbot_id, ip)
    chatbot_key = f"cc:public-chat:chatbot:{chatbot_id}"
    organization_key = f"cc:public-chat:org:{organization_id}"
    try:
        limiter = FixedWindowRateLimiter(redis)
        await limiter.consume("integration", chatbot_id, ip, limit=1, window_seconds=2)
        with pytest.raises(AppError, match="Too many requests"):
            await limiter.consume("integration", chatbot_id, ip, limit=1, window_seconds=2)

        concurrency = ConcurrencyLimiter(redis)
        lease = await concurrency.acquire(chatbot_id, organization_id, 1, 1, 30)
        with pytest.raises(AppError) as caught:
            await concurrency.acquire(chatbot_id, organization_id, 1, 1, 30)
        assert caught.value.details == {"scope": "chatbot"}
        await concurrency.release(lease)
        replacement = await concurrency.acquire(chatbot_id, organization_id, 1, 1, 30)
        await concurrency.release(replacement)

        await redis.zadd(chatbot_key, {"stale": int(time.time() * 1000) - 1})
        await redis.zadd(organization_key, {"stale": int(time.time() * 1000) - 1})
        recovered = await concurrency.acquire(chatbot_id, organization_id, 1, 1, 30)
        await concurrency.release(recovered)
    finally:
        await redis.delete(rate_key, chatbot_key, organization_key)
        await redis.aclose()
