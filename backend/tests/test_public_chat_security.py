from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import AppError
from app.modules.public_chat.api_keys import generate_api_key, hash_api_key
from app.modules.public_chat.concurrency import ConcurrencyLimiter
from app.modules.public_chat.origin import normalize_origin
from app.modules.public_chat.rate_limit import FixedWindowRateLimiter, rate_limit_key
from app.modules.public_chat.schemas import PublicChatRequest


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://example.com", "https://example.com"),
        ("https://EXAMPLE.com", "https://example.com"),
        ("https://example.com:443", "https://example.com"),
        ("http://localhost:4200", "http://localhost:4200"),
        ("http://[::1]:80", "http://[::1]"),
    ],
)
def test_origin_is_canonicalized(value: str, expected: str) -> None:
    assert normalize_origin(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "example.com",
        "ftp://example.com",
        "https://example.com/path",
        "https://example.com?query=1",
        "https://user:password@example.com",
    ],
)
def test_invalid_origins_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_origin(value)


def test_public_chat_payload_forbids_tenant_scope() -> None:
    with pytest.raises(ValidationError):
        PublicChatRequest(message="hello", organization_id=str(uuid4()))
    with pytest.raises(ValidationError):
        PublicChatRequest(message="hello", workspace_id=str(uuid4()))


def test_api_keys_are_random_and_hashed_with_pepper() -> None:
    settings = Settings(_env_file=None, app_env="test", public_api_key_pepper="pepper")
    first = generate_api_key(settings)
    second = generate_api_key(settings)
    assert first.startswith("rhpk_test_")
    assert first != second
    assert hash_api_key(first, "pepper") != first
    assert hash_api_key(first, "pepper") != hash_api_key(first, "other-pepper")


def test_rate_limit_keys_are_scoped_and_do_not_contain_raw_ip() -> None:
    chatbot_a, chatbot_b = uuid4(), uuid4()
    first = rate_limit_key("public-chat", chatbot_a, "203.0.113.4")
    assert first == rate_limit_key("public-chat", chatbot_a, "203.0.113.4")
    assert first != rate_limit_key("public-chat", chatbot_a, "203.0.113.5")
    assert first != rate_limit_key("public-chat", chatbot_b, "203.0.113.4")
    assert "203.0.113.4" not in first


class ScriptedRedis:
    def __init__(self, *results: object) -> None:
        self.results = list(results)
        self.calls: list[tuple[object, ...]] = []

    async def eval(self, *args: object) -> object:
        self.calls.append(args)
        return self.results.pop(0)


async def test_rate_limiter_returns_retry_after() -> None:
    redis = ScriptedRedis([4, 23])
    with pytest.raises(AppError) as caught:
        await FixedWindowRateLimiter(redis).consume(
            "public-chat", uuid4(), "203.0.113.4", limit=3, window_seconds=60
        )
    assert caught.value.code == "RATE_LIMIT_EXCEEDED"
    assert caught.value.headers == {"Retry-After": "23"}


async def test_concurrency_limit_reports_scope_and_release_is_idempotent() -> None:
    limited = ScriptedRedis(2)
    with pytest.raises(AppError) as caught:
        await ConcurrencyLimiter(limited).acquire(uuid4(), uuid4(), 2, 10, 180)
    assert caught.value.details == {"scope": "organization"}

    available = ScriptedRedis(0, 1, 1)
    limiter = ConcurrencyLimiter(available)
    lease = await limiter.acquire(uuid4(), uuid4(), 2, 10, 180)
    await limiter.release(lease)
    await limiter.release(lease)
    assert len(available.calls) == 3
