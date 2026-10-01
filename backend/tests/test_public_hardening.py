import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from app.core.config import Settings
from app.core.logging import SecretRedactionFilter
from app.core.public_observability import PublicChatObservability
from app.modules.chatbots.public_limits import client_ip


@pytest.mark.parametrize(
    "peer,trusted,expected",
    [
        ("192.0.2.1", "", "192.0.2.1"),
        ("192.0.2.1", "10.0.0.0/8", "192.0.2.1"),
        ("10.0.0.2", "10.0.0.0/8", "203.0.113.5"),
    ],
)
def test_forwarded_ip_requires_trusted_proxy(peer, trusted, expected):
    request = Request(
        {
            "type": "http",
            "client": (peer, 123),
            "headers": [(b"x-real-ip", b"203.0.113.5")],
        }
    )
    settings = Settings(_env_file=None, public_chat_trusted_proxy_cidrs=trusted)
    assert client_ip(request, settings) == expected


def test_raw_embed_key_is_redacted_in_access_and_application_logs():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        "POST /api/v1/public/chatbots/%s/chat",
        ("rgh_secret-key_123",),
        None,
    )
    SecretRedactionFilter().filter(record)
    assert "rgh_secret" not in record.getMessage()
    assert "/public/chatbots/[REDACTED]/chat" in record.getMessage()


@pytest.mark.asyncio
async def test_public_metrics_record_denials_without_key(monkeypatch, caplog):
    import app.core.public_observability as module

    pipeline = AsyncMock()
    pipeline.hincrby = MagicMock()
    redis = AsyncMock()
    redis.pipeline = MagicMock()
    redis.pipeline.return_value.__aenter__.return_value = pipeline
    factory = MagicMock()
    factory.from_url.return_value.__aenter__.return_value = redis
    monkeypatch.setattr(module, "Redis", factory)

    async def app(scope, receive, send):
        scope["state"]["public_error_code"] = "EMBED_ORIGIN_NOT_ALLOWED"
        await send({"type": "http.response.start", "status": 403, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    caplog.set_level(logging.INFO, logger=module.__name__)
    await PublicChatObservability(app)(
        {
            "type": "http",
            "path": "/api/v1/public/chatbots/rgh_secret/config",
            "method": "GET",
            "state": {"request_id": "test-id"},
        },
        AsyncMock(),
        AsyncMock(),
    )
    pipeline.hincrby.assert_any_call("public:metrics", "status:403", 1)
    pipeline.hincrby.assert_any_call("public:metrics", "requests", 1)
    pipeline.execute.assert_awaited_once()
    assert "rgh_secret" not in caplog.text
    assert "request_id=test-id" in caplog.text
