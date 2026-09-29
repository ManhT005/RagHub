import logging
import time
import uuid
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

ACQUIRE_SCRIPT = """
local now = tonumber(ARGV[1])
local expires = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then return 1 end
if redis.call('ZCARD', KEYS[2]) >= tonumber(ARGV[4]) then return 2 end
redis.call('ZADD', KEYS[1], expires, ARGV[5])
redis.call('ZADD', KEYS[2], expires, ARGV[5])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[6]))
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[6]))
return 0
"""

RELEASE_SCRIPT = """
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZREM', KEYS[2], ARGV[1])
return 1
"""


@dataclass(frozen=True)
class ConcurrencyLease:
    lease_id: str
    chatbot_key: str
    organization_key: str


class ConcurrencyLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def acquire(
        self,
        chatbot_id: UUID,
        organization_id: UUID,
        chatbot_limit: int,
        organization_limit: int,
        lease_seconds: int,
    ) -> ConcurrencyLease:
        lease_id = str(uuid.uuid4())
        chatbot_key = f"cc:public-chat:chatbot:{chatbot_id}"
        organization_key = f"cc:public-chat:org:{organization_id}"
        now_ms = int(time.time() * 1000)
        expires_ms = now_ms + lease_seconds * 1000
        try:
            result = int(
                await self.redis.eval(
                    ACQUIRE_SCRIPT,
                    2,
                    chatbot_key,
                    organization_key,
                    now_ms,
                    expires_ms,
                    chatbot_limit,
                    organization_limit,
                    lease_id,
                    lease_seconds + 30,
                )
            )
        except Exception as exc:
            raise AppError(
                "PUBLIC_GUARD_UNAVAILABLE",
                "Public access guards are temporarily unavailable.",
                status_code=503,
            ) from exc
        if result:
            scope = "chatbot" if result == 1 else "organization"
            raise AppError(
                "CONCURRENT_STREAM_LIMIT_EXCEEDED",
                "Too many chat streams are active.",
                status_code=429,
                details={"scope": scope},
            )
        return ConcurrencyLease(lease_id, chatbot_key, organization_key)

    async def release(self, lease: ConcurrencyLease) -> None:
        try:
            await self.redis.eval(
                RELEASE_SCRIPT,
                2,
                lease.chatbot_key,
                lease.organization_key,
                lease.lease_id,
            )
        except Exception:
            logger.exception("Failed to release public chat concurrency lease")
