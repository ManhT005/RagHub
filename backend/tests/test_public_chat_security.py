from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.core.config import Settings
from app.core.exceptions import AppError
from app.modules.public_chat.api_keys import generate_api_key, hash_api_key
from app.modules.public_chat.client_ip import resolve_client_ip
from app.modules.public_chat.concurrency import ConcurrencyLimiter
from app.modules.public_chat.conversation_tokens import (
    conversation_token_matches,
    generate_conversation_token,
    hash_conversation_token,
)
from app.modules.public_chat.origin import normalize_origin
from app.modules.public_chat.rate_limit import FixedWindowRateLimiter, rate_limit_key
from app.modules.public_chat.schemas import PublicChatRequest
from app.modules.public_chat.service import PublicChatAccessService


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
    conversation = {
        "conversation_id": str(uuid4()),
        "conversation_token": generate_conversation_token(),
    }
    with pytest.raises(ValidationError):
        PublicChatRequest(message="hello", organization_id=str(uuid4()), **conversation)
    with pytest.raises(ValidationError):
        PublicChatRequest(message="hello", workspace_id=str(uuid4()), **conversation)


def test_public_chat_requires_conversation_capability() -> None:
    with pytest.raises(ValidationError):
        PublicChatRequest(message="hello", conversation_id=uuid4())
    with pytest.raises(ValidationError):
        PublicChatRequest(message="hello", conversation_token=generate_conversation_token())


def test_api_keys_are_random_and_hashed_with_pepper() -> None:
    settings = Settings(_env_file=None, app_env="test", public_api_key_pepper="pepper")
    first = generate_api_key(settings)
    second = generate_api_key(settings)
    assert first.startswith("rhpk_test_")
    assert first != second
    assert hash_api_key(first, "pepper") != first
    assert hash_api_key(first, "pepper") != hash_api_key(first, "other-pepper")


def test_public_conversation_tokens_are_random_and_hashed() -> None:
    first = generate_conversation_token()
    second = generate_conversation_token()
    digest = hash_conversation_token(first, "pepper")
    assert first.startswith("rhct_")
    assert first != second
    assert first != digest
    assert conversation_token_matches(first, digest, "pepper")
    assert not conversation_token_matches(second, digest, "pepper")


async def test_public_conversation_rejects_wrong_capability_token() -> None:
    raw_token = generate_conversation_token()
    conversation = SimpleNamespace(
        public_access_token_hash=hash_conversation_token(raw_token, "pepper")
    )

    class Session:
        async def scalar(self, _statement: object) -> object:
            return conversation

    settings = Settings(_env_file=None, app_env="test", public_api_key_pepper="pepper")
    service = PublicChatAccessService(Session(), settings)
    assert await service.verify_conversation(uuid4(), uuid4(), raw_token) is conversation
    with pytest.raises(AppError) as caught:
        await service.verify_conversation(uuid4(), uuid4(), generate_conversation_token())
    assert caught.value.code == "CONVERSATION_NOT_FOUND"


def test_rate_limit_keys_are_scoped_and_do_not_contain_raw_ip() -> None:
    chatbot_a, chatbot_b = uuid4(), uuid4()
    first = rate_limit_key("public-chat", chatbot_a, "203.0.113.4")
    assert first == rate_limit_key("public-chat", chatbot_a, "203.0.113.4")
    assert first != rate_limit_key("public-chat", chatbot_a, "203.0.113.5")
    assert first != rate_limit_key("public-chat", chatbot_b, "203.0.113.4")
    assert "203.0.113.4" not in first


def make_request(peer: str, real_ip: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-real-ip", real_ip.encode())],
            "client": (peer, 12345),
        }
    )


def test_proxy_header_is_ignored_when_proxy_trust_is_disabled() -> None:
    settings = Settings(
        _env_file=None,
        trust_proxy_headers=False,
        trusted_proxy_cidrs="172.30.0.10/32",
    )
    assert resolve_client_ip(make_request("172.30.0.10", "203.0.113.5"), settings) == (
        "172.30.0.10"
    )


def test_proxy_header_is_used_only_for_trusted_proxy_peer() -> None:
    settings = Settings(
        _env_file=None,
        trust_proxy_headers=True,
        trusted_proxy_cidrs="172.30.0.10/32",
    )
    assert (
        resolve_client_ip(make_request("172.30.0.10", "203.0.113.5"), settings)
        == "203.0.113.5"
    )
    assert resolve_client_ip(make_request("172.30.0.11", "203.0.113.6"), settings) == (
        "172.30.0.11"
    )


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

    available = ScriptedRedis(0, 1, 1, 1)
    limiter = ConcurrencyLimiter(available)
    lease = await limiter.acquire(uuid4(), uuid4(), 2, 10, 180)
    assert await limiter.renew(lease, 180)
    await limiter.release(lease)
    await limiter.release(lease)
    assert len(available.calls) == 4
