from types import SimpleNamespace
from uuid import uuid4

import pytest


def test_embed_key_is_hashed_and_never_returned_from_public_config() -> None:
    from app.modules.chatbots.embed import create_embed_key, public_config

    raw_key, key_hash = create_embed_key()
    chatbot = SimpleNamespace(
        name="Tro ly",
        published=True,
        embed_key_hash=key_hash,
        embed_primary_color="#1463ff",
        embed_title="Hoi RagHub",
        embed_greeting="Xin chao",
        allowed_origins=["https://example.com"],
    )
    assert raw_key.startswith("rgh_")
    assert raw_key not in key_hash
    assert public_config(chatbot) == {
        "name": "Tro ly",
        "primary_color": "#1463ff",
        "title": "Hoi RagHub",
        "greeting": "Xin chao",
    }


@pytest.mark.parametrize(
    "origin,allowed",
    [
        ("https://example.com", True),
        ("https://evil.example", False),
        (None, False),
    ],
)
def test_embed_origin_requires_explicit_allowlist(origin: str | None, allowed: bool) -> None:
    from app.modules.chatbots.embed import origin_is_allowed

    assert origin_is_allowed(origin, ["https://example.com"]) is allowed


@pytest.mark.asyncio
async def test_public_config_rejects_wrong_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.exceptions import AppError
    from app.modules.chatbots.router import public_config

    class FakeService:
        def __init__(self, session: object) -> None:
            pass

        async def config(self, key: str, origin: str | None):
            raise AppError(
                "EMBED_ORIGIN_NOT_ALLOWED", "This website is not allowed.", status_code=403
            )

    import app.modules.chatbots.router as router

    monkeypatch.setattr(router, "PublicChatContainer", FakeService)
    with pytest.raises(AppError, match="not allowed"):
        await public_config("rgh_bad", "https://evil.example", object())


def test_public_cors_echoes_the_verified_origin() -> None:
    from app.modules.chatbots.router import public_cors_headers

    headers = public_cors_headers("https://example.com")
    assert headers["Access-Control-Allow-Origin"] == "https://example.com"
    assert headers["Vary"] == "Origin"


@pytest.mark.parametrize(
    "published,origin,status",
    [
        (False, "https://example.com", 404),
        (True, "https://example.com", 200),
        (True, "https://wrong.example", 403),
    ],
)
async def test_public_resolver_keeps_publication_and_origin_gates(published, origin, status):
    from unittest.mock import AsyncMock

    from app.core.exceptions import AppError
    from app.delivery.security.public_chat import PublicChatResolver

    bot = SimpleNamespace(allowed_origins=["https://example.com"])

    async def select_published(statement):
        # A historical key must only match published chatbots in a live workspace.
        sql = str(statement)
        assert "chatbots.published IS true" in sql
        assert "workspaces.deleted_at IS NULL" in sql
        return bot if published else None

    resolver = PublicChatResolver(SimpleNamespace(scalar=AsyncMock(side_effect=select_published)))
    if status == 200:
        assert await resolver.resolve("rgh_historical", origin) is bot
    else:
        with pytest.raises(AppError) as error:
            await resolver.resolve("rgh_historical", origin)
        assert error.value.status_code == status


@pytest.mark.asyncio
async def test_public_chat_uses_real_sse_frame_delimiters(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    from unittest.mock import AsyncMock

    from starlette.requests import Request

    import app.modules.chatbots.router as router
    from app.core.exceptions import AppError
    from app.modules.chatbots.schemas import ChatRequest

    class FakeService:
        def __init__(self, session: object) -> None:
            pass

        async def resolve(self, key: str, origin: str | None):
            return SimpleNamespace(id=uuid4(), organization_id=uuid4())

        async def stream_events(self, command):
            from raghub_core.domain.rag.events import TokenDelta

            yield TokenDelta("Xin chào")
            raise AppError("TEST_ERROR", "Try again", status_code=503)

    monkeypatch.setattr(router, "PublicChatContainer", FakeService)
    limits = AsyncMock()
    from app.core.config import Settings

    limits.settings = Settings()
    response = await router.public_chat(
        "rgh_test",
        ChatRequest(message="Hello"),
        Request({"type": "http", "client": ("127.0.0.1", 1234)}),
        "http://localhost:8081",
        object(),
        limits,
    )
    frames = [frame async for frame in response.body_iterator]
    assert len(frames) == 2
    for frame, event in zip(frames, ["token", "error"], strict=False):
        assert frame.startswith(f"event: {event}\ndata: ")
        assert frame.endswith("\n\n")
        json.loads(frame.split("\n")[1].removeprefix("data: "))
