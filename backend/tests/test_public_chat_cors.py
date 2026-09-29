from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.redis import get_redis
from app.main import app
from app.modules.public_chat.conversation_tokens import hash_conversation_token

CONVERSATION_ID = uuid4()
CONVERSATION_TOKEN = "rhct_abcdefghijklmnopqrstuvwxyz1234567890"


class FakeSession:
    def __init__(self) -> None:
        self.chatbot = type(
            "PublicChatbot",
            (),
            {
                "id": uuid4(),
                "organization_id": uuid4(),
                "published": True,
            },
        )()
        conversation = type(
            "PublicConversation",
            (),
            {
                "id": CONVERSATION_ID,
                "chatbot_id": self.chatbot.id,
                "public_access_token_hash": hash_conversation_token(
                    CONVERSATION_TOKEN, "change-me-public-api-key-pepper"
                ),
            },
        )()
        self.results = [self.chatbot, uuid4(), conversation]

    async def scalar(self, _statement: object) -> object:
        return self.results.pop(0)


class ScriptedRedis:
    def __init__(self, *results: object) -> None:
        self.results = list(results)

    async def eval(self, *_args: object) -> object:
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def public_client() -> Iterator[tuple[TestClient, ScriptedRedis]]:
    session = FakeSession()
    redis = ScriptedRedis([4, 23])
    settings = Settings(
        _env_file=None,
        app_env="test",
        public_chat_rate_limit_requests=3,
    )
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            yield client, redis
    finally:
        app.dependency_overrides.clear()


def assert_cors_error(response, code: str, status_code: int) -> None:
    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert response.headers["access-control-allow-origin"] == "https://allowed.example"
    assert response.headers["vary"] == "Origin"


def chat_payload() -> dict[str, str]:
    return {
        "message": "hello",
        "conversation_id": str(CONVERSATION_ID),
        "conversation_token": CONVERSATION_TOKEN,
    }


def test_rate_limit_error_keeps_retry_after_and_cors(public_client) -> None:
    client, _ = public_client
    response = client.post(
        "/api/v1/public/chatbots/cb_pub_test/chat",
        headers={"Origin": "https://allowed.example"},
        json=chat_payload(),
    )
    assert_cors_error(response, "RATE_LIMIT_EXCEEDED", 429)
    assert response.headers["retry-after"] == "23"


def test_concurrency_error_has_cors(public_client) -> None:
    client, redis = public_client
    redis.results[:] = [[1, 60], 1]
    response = client.post(
        "/api/v1/public/chatbots/cb_pub_test/chat",
        headers={"Origin": "https://allowed.example"},
        json=chat_payload(),
    )
    assert_cors_error(response, "CONCURRENT_STREAM_LIMIT_EXCEEDED", 429)


def test_redis_guard_error_has_cors(public_client) -> None:
    client, redis = public_client
    redis.results[:] = [ConnectionError("redis unavailable")]
    response = client.post(
        "/api/v1/public/chatbots/cb_pub_test/chat",
        headers={"Origin": "https://allowed.example"},
        json=chat_payload(),
    )
    assert_cors_error(response, "PUBLIC_GUARD_UNAVAILABLE", 503)
