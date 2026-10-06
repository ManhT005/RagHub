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


def test_real_redis_prioritizes_upload_before_older_reindex_message(monkeypatch):
    from kombu import Connection, Producer, Queue

    url = os.getenv("RAGHUB_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set disposable Redis test URL.")
    name = "rag-priority-test-" + uuid.uuid4().hex
    with Connection(url, transport_options={"priority_steps": [0, 1, 2, 3, 4, 6, 9]}) as connection:
        with connection.channel() as channel:
            queue = Queue(name, routing_key=name)(channel)
            queue.declare()
            try:
                producer = Producer(channel)
                producer.publish(
                    {"kind": "reindex"}, routing_key=name, serializer="json", priority=3
                )
                producer.publish(
                    {"kind": "upload"}, routing_key=name, serializer="json", priority=1
                )
                producer.publish(
                    {"kind": "legacy"}, routing_key=name, serializer="json", priority=9
                )
                from types import SimpleNamespace

                from scripts import capture_rag_operations

                monkeypatch.setattr(capture_rag_operations, "QUEUES", (name, name + "-undeclared"))
                depths = capture_rag_operations.queue_depths(SimpleNamespace(celery_broker_url=url))
                assert depths == {name: 3, name + "-undeclared": 0}
                message = queue.get(no_ack=False)
                assert message.payload == {"kind": "upload"}
                message.ack()
                message = queue.get(no_ack=False)
                assert message.payload == {"kind": "reindex"}
                message.ack()
                message = queue.get(no_ack=False)
                assert message.payload == {"kind": "legacy"}
                message.ack()
            finally:
                queue.delete()


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
