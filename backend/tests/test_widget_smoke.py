"""Live HTTP -> Nginx -> API -> DB/Redis/search -> SSE, without a paid AI provider."""

import json
import os
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.security import hash_password
from app.modules.auth.models import UserIdentity
from app.modules.organizations.models import Organization
from app.modules.users.models import User

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def smoke_client():
    base = os.getenv("RAGHUB_WIDGET_TEST_URL")
    database = os.getenv("RAGHUB_TEST_DATABASE_URL")
    if not base or not database:
        pytest.skip("Set RAGHUB_WIDGET_TEST_URL and RAGHUB_TEST_DATABASE_URL.")
    engine = create_async_engine(database, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid4()
    email = f"widget-{user_id.hex}@example.com"
    password = uuid4().hex
    organization_id = None
    async with sessions() as session:
        session.add(User(id=user_id, email=email, status="ACTIVE"))
        await session.flush()
        session.add(
            UserIdentity(
                user_id=user_id,
                provider="LOCAL",
                provider_subject=email,
                password_hash=hash_password(password),
            )
        )
        await session.commit()
    try:
        async with httpx.AsyncClient(base_url=base, timeout=30) as client:
            auth = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
            )
            assert auth.status_code == 200
            headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
            org = await client.post(
                "/api/v1/organizations",
                headers=headers,
                json={
                    "name": "Widget smoke",
                    "slug": f"widget-{user_id.hex}",
                },
            )
            assert org.status_code == 201
            organization_id = UUID(org.json()["id"])
            headers["X-Organization-ID"] = str(organization_id)
            yield client, headers
    finally:
        async with sessions() as session:
            if organization_id:
                await session.execute(
                    delete(Organization).where(Organization.id == organization_id)
                )
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await engine.dispose()


async def test_publish_origin_sse_rotate_and_nginx(smoke_client):
    client, headers = smoke_client
    workspace = await client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={
            "name": "Widget",
            "slug": "widget",
        },
    )
    assert workspace.status_code == 201
    workspace_id = workspace.json()["id"]
    provider = await client.post(
        f"/api/v1/organizations/{headers['X-Organization-ID']}/providers",
        headers=headers,
        json={
            "name": "Smoke embedding",
            "provider_type": "LOCAL_TOKEN_HASH",
            "capability": "EMBEDDING",
            "model": "token-hash-v1",
            "dimension": 384,
        },
    )
    assert provider.status_code == 201
    binding = await client.patch(
        f"/api/v1/workspaces/{workspace_id}/providers",
        headers=headers,
        json={"embedding_provider_id": provider.json()["id"]},
    )
    assert binding.status_code == 200
    bot = await client.post(
        f"/api/v1/workspaces/{workspace_id}/chatbots",
        headers=headers,
        json={"name": "Smoke"},
    )
    assert bot.status_code == 201
    bot_url = f"/api/v1/chatbots/{bot.json()['id']}"
    origin = {"Origin": "https://widget.example.com"}
    publish = await client.post(
        bot_url + "/publish",
        headers=headers,
        json={
            "allowed_origins": [origin["Origin"]],
            "title": "Smoke title",
        },
    )
    assert publish.status_code == 200
    saved = await client.get(bot_url, headers=headers)
    assert saved.status_code == 200
    assert saved.json()["allowed_origins"] == [origin["Origin"]]
    assert saved.json()["embed_title"] == "Smoke title"
    listing = await client.get(f"/api/v1/workspaces/{workspace_id}/chatbots", headers=headers)
    assert listing.status_code == 200 and listing.json()[0]["embed_title"] == "Smoke title"
    key = publish.json()["key"]
    public = f"/api/v1/public/chatbots/{key}"
    oversized = await client.post(
        public + "/chat",
        headers=origin,
        json={"message": "x" * 17000},
    )
    assert oversized.status_code == 413
    config = await client.get(public + "/config", headers=origin)
    assert config.status_code == 200 and config.json()["title"] == "Smoke title"
    assert key not in config.text
    assert config.headers["access-control-allow-origin"] == origin["Origin"]
    for endpoint in ("config", "chat"):
        if endpoint == "config":
            denied = await client.get(public + "/config", headers={"Origin": "https://evil.test"})
        else:
            denied = await client.post(
                public + "/chat",
                json={"message": "Hi"},
                headers={
                    "Origin": "https://evil.test",
                },
            )
        assert denied.status_code == 403
        assert "access-control-allow-origin" not in denied.headers
    preflight = await client.options(
        public + "/chat",
        headers={
            **origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 204
    async with client.stream(
        "POST",
        public + "/chat",
        json={"message": "Hello"},
        headers=origin,
    ) as chat:
        assert chat.status_code == 200
        assert chat.headers["content-type"].startswith("text/event-stream")
        frames = [line async for line in chat.aiter_lines()]
    for event in ("conversation", "citations", "token", "done"):
        assert f"event: {event}" in frames
    assert "event: error" not in frames
    conversation = json.loads(
        frames[frames.index("event: conversation") + 1].removeprefix("data: ")
    )
    foreign_user = await client.post(
        public + "/chat",
        headers=origin,
        json={
            "message": "Follow up",
            "conversation_id": conversation["conversation_id"],
            "external_user_id": "different-user",
        },
    )
    assert foreign_user.status_code == 200
    assert "CONVERSATION_ACCESS_DENIED" in foreign_user.text
    assert "event: done" not in foreign_user.text
    rotated = await client.post(bot_url + "/embed-key/rotate", headers=headers)
    assert rotated.status_code == 200
    new_key = rotated.json()["key"]
    assert new_key != key and key not in rotated.json()["code"]
    for endpoint in ("config", "chat"):
        old = await client.request(
            "GET" if endpoint == "config" else "POST",
            public + "/" + endpoint,
            headers=origin,
            **({"json": {"message": "Hi"}} if endpoint == "chat" else {}),
        )
        assert old.status_code == 404
    code = await client.get(bot_url + "/embed-code", headers=headers)
    assert code.status_code == 200 and key not in code.text
    assert code.json()["code"] is None and code.json()["key"] is None
    assert code.json()["has_embed_key"] is True
    assert code.json()["script_src"].startswith(("http://", "https://"))
    new_public = f"/api/v1/public/chatbots/{new_key}"
    assert (await client.get(new_public + "/config", headers=origin)).status_code == 200
    # Real HTTP 429 with a valid key, and admin chat still works after exhausting public rate.
    for _ in range(25):
        limited = await client.post(
            new_public + "/chat",
            headers=origin,
            json={"message": "Hello", "conversation_id": str(uuid4())},
        )
        if limited.status_code == 429:
            break
        assert limited.status_code == 200 and "event: error" in limited.text
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "PUBLIC_CHAT_RATE_LIMITED"
    assert int(limited.headers["retry-after"]) > 0
    assert limited.headers["access-control-allow-origin"] == origin["Origin"]
    admin = await client.post(bot_url + "/chat", headers=headers, json={"message": "Hello"})
    assert admin.status_code == 200 and "event: done" in admin.text
    await client.patch(bot_url, headers=headers, json={"published": False})
    draft_preview = await client.post(bot_url + "/chat", headers=headers, json={"message": "Hello"})
    assert draft_preview.status_code == 200 and "event: done" in draft_preview.text
    for endpoint in ("config", "chat"):
        unavailable = await client.request(
            "GET" if endpoint == "config" else "POST",
            new_public + "/" + endpoint,
            headers=origin,
            **({"json": {"message": "Hi"}} if endpoint == "chat" else {}),
        )
        assert unavailable.status_code == 404
    script = await client.get("/widget/raghub.js")
    assert script.status_code == 200 and "customElements" in script.text
    assert "charset=utf-8" in script.headers["content-type"].lower()
    assert "no-store" in script.headers["cache-control"]
    demo = await client.get("/demo/")
    assert demo.status_code == 200 and "/widget/raghub.js" in demo.text
    await client.patch(bot_url, headers=headers, json={"published": True})
    deleted = await client.delete(f"/api/v1/workspaces/{workspace_id}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(new_public + "/config", headers=origin)).status_code == 404
    hidden = await client.post(new_public + "/chat", headers=origin, json={"message": "Hello"})
    assert hidden.status_code == 404
