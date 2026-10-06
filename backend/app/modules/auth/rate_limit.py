"""Redis-backed admission limits for authentication endpoints."""

import hashlib
import hmac

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
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


class AuthRateLimiter:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self.redis = redis
        self.settings = settings

    def _digest(self, value: str) -> str:
        return hmac.new(
            self.settings.app_secret_key.encode(), value.strip().lower().encode(), hashlib.sha256
        ).hexdigest()

    async def login(self, ip: str, email: str) -> None:
        await self._check(
            "login",
            ip,
            email,
            self.settings.auth_login_requests_per_ip,
            self.settings.auth_login_requests_per_account,
        )

    async def password(self, ip: str, subject: str) -> None:
        await self._check(
            "password",
            ip,
            subject,
            self.settings.auth_password_requests_per_ip,
            self.settings.auth_password_requests_per_account,
        )

    async def _check(
        self, action: str, ip: str, subject: str, ip_limit: int, subject_limit: int
    ) -> None:
        try:
            retry = int(
                await self.redis.eval(
                    RATE_SCRIPT,
                    2,
                    f"auth:rate:{action}:ip:{self._digest(ip)}",
                    f"auth:rate:{action}:subject:{self._digest(subject)}",
                    ip_limit,
                    subject_limit,
                )
            )
        except RedisError as exc:
            raise AppError(
                "AUTH_ADMISSION_UNAVAILABLE",
                "Authentication is temporarily unavailable.",
                status_code=503,
            ) from exc
        if retry:
            raise AppError(
                "AUTH_RATE_LIMITED",
                "Too many authentication attempts. Try again shortly.",
                status_code=429,
                details={"retry_after_seconds": retry},
            )
