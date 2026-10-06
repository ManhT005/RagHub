from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.modules.auth.rate_limit import AuthRateLimiter


@pytest.mark.asyncio
async def test_auth_rate_keys_do_not_contain_ip_or_email():
    redis = AsyncMock()
    redis.eval.return_value = 0
    limits = AuthRateLimiter(redis, Settings(_env_file=None))

    await limits.login("203.0.113.9", "Owner@Example.com")

    args = redis.eval.call_args.args
    keys = " ".join(str(value) for value in args[2:4])
    assert "203.0.113.9" not in keys
    assert "owner@example.com" not in keys.lower()
    assert args[4:] == (10, 5)


@pytest.mark.asyncio
async def test_auth_rate_limit_returns_retry_after():
    redis = AsyncMock()
    redis.eval.return_value = 37
    limits = AuthRateLimiter(redis, Settings(_env_file=None))

    with pytest.raises(AppError) as error:
        await limits.password("203.0.113.9", "owner@example.com")

    assert error.value.code == "AUTH_RATE_LIMITED"
    assert error.value.details == {"retry_after_seconds": 37}
