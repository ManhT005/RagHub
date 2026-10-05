"""Shared, atomic public-chat admission controls. Raw embed keys never enter Redis."""

import hashlib
from uuid import uuid4

from raghub_core.domain.errors import CoreError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings

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

ACQUIRE_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
for i, key in ipairs(KEYS) do
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
    if redis.call('ZCARD', key) >= tonumber(ARGV[i]) then return 0 end
end
for _, key in ipairs(KEYS) do
    redis.call('ZADD', key, now + tonumber(ARGV[3]), ARGV[4])
    redis.call('EXPIRE', key, math.ceil(tonumber(ARGV[3])))
end
return 1
"""

RELEASE_SCRIPT = """
for _, key in ipairs(KEYS) do redis.call('ZREM', key, ARGV[1]) end
return 1
"""


class PublicChatLimits:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self.redis = redis
        self.settings = settings

    def slot_keys(self, chatbot_id: str) -> tuple[str, str]:
        return "public:active:global", f"public:active:bot:{chatbot_id}"

    async def acquire(self, chatbot_id: str) -> str:
        token = uuid4().hex
        try:
            acquired = await self.redis.eval(
                ACQUIRE_SCRIPT,
                2,
                *self.slot_keys(chatbot_id),
                self.settings.public_chat_concurrent_global,
                self.settings.public_chat_concurrent_per_chatbot,
                self.settings.public_chat_stream_timeout_seconds + 10,
                token,
            )
        except RedisError as exc:
            raise CoreError(
                "PUBLIC_CHAT_UNAVAILABLE",
                "Public chat admission is unavailable.",
            ) from exc
        if not acquired:
            raise CoreError(
                "PUBLIC_CHAT_CONCURRENCY_LIMITED",
                "Public chat is busy. Try again shortly.",
                details={"retry_after_seconds": 5},
            )
        return token

    async def release(self, chatbot_id: str, token: str) -> None:
        await self.redis.eval(RELEASE_SCRIPT, 2, *self.slot_keys(chatbot_id), token)

    async def check_rate(self, chatbot_id: str, ip: str) -> None:
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()
        try:
            retry = int(
                await self.redis.eval(
                    RATE_SCRIPT,
                    2,
                    f"public:rate:ip:{ip_hash}",
                    f"public:rate:bot:{chatbot_id}",
                    self.settings.public_chat_requests_per_ip,
                    self.settings.public_chat_requests_per_chatbot,
                )
            )
        except RedisError as exc:
            raise CoreError(
                "PUBLIC_CHAT_UNAVAILABLE",
                "Public chat admission is unavailable.",
            ) from exc
        if retry:
            raise CoreError(
                "PUBLIC_CHAT_RATE_LIMITED",
                "Too many public chat requests.",
                details={"retry_after_seconds": retry},
            )
