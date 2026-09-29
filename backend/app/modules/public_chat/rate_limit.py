import hashlib
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis

from app.core.exceptions import AppError

RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


@dataclass(frozen=True)
class RateLimitResult:
    current: int
    remaining: int
    retry_after: int


def rate_limit_key(scope: str, chatbot_id: UUID, client_ip: str) -> str:
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:24]
    return f"rl:{scope}:{chatbot_id}:{ip_hash}"


class FixedWindowRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def consume(
        self, scope: str, chatbot_id: UUID, client_ip: str, limit: int, window_seconds: int
    ) -> RateLimitResult:
        key = rate_limit_key(scope, chatbot_id, client_ip)
        try:
            raw = await self.redis.eval(RATE_LIMIT_SCRIPT, 1, key, window_seconds)
            current, ttl = int(raw[0]), max(1, int(raw[1]))
        except Exception as exc:
            raise AppError(
                "PUBLIC_GUARD_UNAVAILABLE",
                "Public access guards are temporarily unavailable.",
                status_code=503,
            ) from exc
        if current > limit:
            raise AppError(
                "RATE_LIMIT_EXCEEDED",
                "Too many requests.",
                status_code=429,
                details={"retry_after_seconds": ttl},
                headers={"Retry-After": str(ttl)},
            )
        return RateLimitResult(current=current, remaining=max(0, limit - current), retry_after=ttl)
