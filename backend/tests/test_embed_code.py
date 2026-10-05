from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

import app.modules.chatbots.embed as embed
import app.modules.chatbots.router as router
from app.core.config import Settings
from app.core.exceptions import AppError
from app.modules.chatbots.schemas import EmbedPublishInput


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:8080",
        "http://192.168.1.50:8080",
        "https://raghub.example.com",
    ],
)
def test_embed_is_absolute_and_raw_key_is_show_once(monkeypatch, base):
    monkeypatch.setattr(
        embed, "get_settings", lambda: Settings(_env_file=None, public_base_url=base)
    )
    issued = embed.embed_response("rgh_new")
    assert issued.script_src == f"{base}/widget/raghub.js"
    assert f'src="{issued.script_src}"' in issued.code
    assert 'charset="utf-8"' in issued.code
    assert issued.key == "rgh_new" and issued.has_embed_key
    reloaded = embed.embed_response(has_embed_key=True)
    assert reloaded.code is None and reloaded.key is None
    assert reloaded.script_src == issued.script_src and reloaded.has_embed_key


@pytest.mark.parametrize(
    "base",
    [
        "javascript:alert(1)",
        "data:text/html,test",
        "file:///tmp/test",
        "https://user:pass@host",
        "https://host/path",
        "https://host?key=secret",
        "https://host#test",
        "https://host?",
        "https://host#",
        "https://host:99999",
        "https://host\\evil",
        " https://host",
    ],
)
def test_public_base_url_rejects_unsafe_or_non_origin_urls(base):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, public_base_url=base)


def test_public_base_url_normalizes_and_requires_explicit_http_in_production():
    settings = Settings(_env_file=None, public_base_url="HTTPS://Example.COM:443/")
    assert settings.public_base_url == "https://example.com"
    config = dict(
        _env_file=None,
        app_env="production",
        app_secret_key="a" * 40,
        provider_master_key="p" * 40,
        smtp_host="host",
        smtp_username="user",
        smtp_password="password",
        smtp_from_email="mail@example.com",
        public_base_url="http://192.168.1.50:8080",
    )
    with pytest.raises(ValidationError, match="requires HTTPS"):
        Settings(**config)
    assert Settings(**config, public_base_url_allow_http=True).public_base_url.startswith("http://")


async def test_publish_update_and_reload_do_not_rotate_or_recover_key(monkeypatch):
    monkeypatch.setattr(
        embed,
        "get_settings",
        lambda: Settings(_env_file=None, public_base_url="https://raghub.example.com"),
    )
    bot = SimpleNamespace(workspace_id=uuid4(), published=True, embed_key_hash="hash")
    service = SimpleNamespace(
        get=AsyncMock(return_value=bot),
        publish_embed=AsyncMock(return_value=(bot, None)),
        rotate_embed_key=AsyncMock(return_value="rgh_rotated"),
    )
    monkeypatch.setattr(router, "ChatbotService", lambda session: service)
    monkeypatch.setattr(router, "require_workspace_permission", AsyncMock())
    context, bot_id = SimpleNamespace(organization_id=uuid4()), uuid4()
    result = await router.publish_embed(
        bot_id, EmbedPublishInput(allowed_origins=["https://example.com"]), context, None
    )
    assert result.has_embed_key and result.code is None and result.key is None
    reloaded = await router.embed_code(bot_id, context, None)
    assert reloaded == result
    service.rotate_embed_key.assert_not_awaited()
    rotated = await router.rotate_embed_key(bot_id, context, None)
    assert rotated.key == "rgh_rotated" and "rgh_rotated" in rotated.code


async def test_missing_public_url_fails_before_publish_mutation(monkeypatch):
    monkeypatch.setattr(embed, "get_settings", lambda: Settings(_env_file=None, public_base_url=""))
    service = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(workspace_id=uuid4())), publish_embed=AsyncMock()
    )
    monkeypatch.setattr(router, "ChatbotService", lambda session: service)
    monkeypatch.setattr(router, "require_workspace_permission", AsyncMock())
    with pytest.raises(AppError) as error:
        await router.publish_embed(
            uuid4(),
            EmbedPublishInput(allowed_origins=["https://example.com"]),
            SimpleNamespace(organization_id=uuid4()),
            None,
        )
    assert error.value.code == "PUBLIC_BASE_URL_NOT_CONFIGURED"
    service.publish_embed.assert_not_awaited()
