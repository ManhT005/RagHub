"""Real-Redis quota bucket tests (Lua script execution, depletion, fail-closed).

Needs a reachable Redis: set RAGHUB_TEST_REDIS_URL (default redis://127.0.0.1:6379/0).
Catches script bugs (e.g. Lua syntax errors) that fakes cannot see.
"""

import os
import uuid

import pytest
from raghub_core.ports.embedding_quota import (
    QuotaBackendUnavailableError,
    QuotaDepletedError,
)

from app.core.config import Settings
from app.infrastructure.redis.quota_buckets import QuotaBucketStore

pytestmark = pytest.mark.integration

pytest_plugins = ("pytest_asyncio",)


def _settings():
    return Settings(
        _env_file=None,
        redis_url=os.getenv("RAGHUB_TEST_REDIS_URL", "redis://127.0.0.1:6379/0"),
    )


async def _store():
    from redis.asyncio import Redis

    settings = _settings()
    try:
        client = Redis.from_url(settings.redis_url, socket_timeout=2)
        await client.ping()
    except Exception:
        pytest.skip("Redis is not reachable at RAGHUB_TEST_REDIS_URL.")
    return QuotaBucketStore(client, settings), client


async def test_lua_script_acquires_and_depletes():
    store, client = await _store()
    try:
        scope = f"eval-test-{uuid.uuid4().hex[:8]}"
        await store.acquire(scope=scope, tokens=10)
        with pytest.raises(QuotaDepletedError):
            await store.acquire(scope=scope, tokens=10_000_000)
    finally:
        await client.aclose()


async def test_redis_failure_is_fail_closed():
    from redis.asyncio import Redis

    settings = _settings()
    client = Redis.from_url("redis://127.0.0.1:1/0", socket_timeout=1)
    store = QuotaBucketStore(client, settings)
    try:
        with pytest.raises(QuotaBackendUnavailableError):
            await store.acquire(scope="unreachable", tokens=10)
    finally:
        await client.aclose()
