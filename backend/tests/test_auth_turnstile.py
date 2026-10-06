from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.modules.auth.turnstile import TurnstileVerifier


def settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        turnstile_enabled=True,
        turnstile_site_key="site-key",
        turnstile_secret_key="secret-key",
        turnstile_expected_hostname="raghub.example.com",
        **overrides,
    )


@pytest.mark.asyncio
async def test_turnstile_accepts_matching_hostname_and_action():
    response = AsyncMock()
    response.raise_for_status = lambda: None
    response.json = lambda: {
        "success": True,
        "hostname": "raghub.example.com",
        "action": "login",
    }
    client = AsyncMock()
    client.__aenter__.return_value.post.return_value = response
    with patch("app.modules.auth.turnstile.httpx.AsyncClient", return_value=client):
        await TurnstileVerifier(settings()).verify("token", "203.0.113.5", "login")
    payload = client.__aenter__.return_value.post.call_args.kwargs["data"]
    assert payload["secret"] == "secret-key"
    assert payload["remoteip"] == "203.0.113.5"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        {"success": False, "hostname": "raghub.example.com", "action": "login"},
        {"success": True, "hostname": "evil.example.com", "action": "login"},
        {"success": True, "hostname": "raghub.example.com", "action": "forgot_password"},
    ],
)
async def test_turnstile_rejects_invalid_result(result):
    response = AsyncMock()
    response.raise_for_status = lambda: None
    response.json = lambda: result
    client = AsyncMock()
    client.__aenter__.return_value.post.return_value = response
    with patch("app.modules.auth.turnstile.httpx.AsyncClient", return_value=client):
        with pytest.raises(AppError) as error:
            await TurnstileVerifier(settings()).verify("token", "203.0.113.5", "login")
    assert error.value.code == "TURNSTILE_INVALID"


@pytest.mark.asyncio
async def test_turnstile_fails_closed_when_cloudflare_is_unavailable():
    client = AsyncMock()
    client.__aenter__.return_value.post.side_effect = httpx.ConnectError("offline")
    with patch("app.modules.auth.turnstile.httpx.AsyncClient", return_value=client):
        with pytest.raises(AppError) as error:
            await TurnstileVerifier(settings()).verify("token", "203.0.113.5", "login")
    assert error.value.code == "TURNSTILE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_turnstile_is_optional_when_disabled():
    await TurnstileVerifier(Settings(_env_file=None)).verify("", "203.0.113.5", "login")
