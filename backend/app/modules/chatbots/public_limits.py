"""Shared, atomic public-chat admission controls. Raw embed keys never enter Redis."""

import hashlib
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError

RATE_SCRIPT = """
for i, key in ipairs(KEYS) do
    if tonumber(redis.call('GET', key) or '0') >= tonumber(ARGV[i]) then
        return math.max(1, redis.call('TTL', key))
    end
end
for _, key in ipairs(KEYS) do
    if redis.call('INCR', key) == 1 then redis.call('EXPIRE', key, 60) end
end
return 0
"""


class PublicChatLimits:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self.redis = redis
        self.settings = settings

    async def check_rate(self, chatbot_id: str, ip: str) -> None:
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()
        try:
            retry = int(await self.redis.eval(
                RATE_SCRIPT, 2, f"public:rate:ip:{ip_hash}",
                f"public:rate:bot:{chatbot_id}",
                self.settings.public_chat_requests_per_ip,
                self.settings.public_chat_requests_per_chatbot,
            ))
        except RedisError as exc:
            raise AppError(
                "PUBLIC_CHAT_UNAVAILABLE", "Public chat admission is unavailable.",
                status_code=503,
            ) from exc
        if retry:
            raise AppError(
                "PUBLIC_CHAT_RATE_LIMITED", "Too many public chat requests.",
                status_code=429, details={"retry_after_seconds": retry},
            )


async def get_public_limits(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[PublicChatLimits]:
    async with Redis.from_url(
        settings.redis_url, socket_connect_timeout=2, socket_timeout=2,
    ) as redis:
        yield PublicChatLimits(redis, settings)
