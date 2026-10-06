"""Cloudflare Turnstile server-side verification for public auth forms."""

import logging

import httpx

from app.core.config import Settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)
SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class TurnstileVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def verify(self, token: str, remote_ip: str, action: str) -> None:
        if not self.settings.turnstile_enabled:
            return
        if not token:
            raise AppError("TURNSTILE_REQUIRED", "Human verification is required.", status_code=400)
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                response = await client.post(
                    SITEVERIFY_URL,
                    data={
                        "secret": self.settings.turnstile_secret_key,
                        "response": token,
                        "remoteip": remote_ip,
                    },
                )
                response.raise_for_status()
                result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Turnstile verification unavailable: %s", type(exc).__name__)
            raise AppError(
                "TURNSTILE_UNAVAILABLE",
                "Human verification is temporarily unavailable.",
                status_code=503,
            ) from exc
        if not (
            result.get("success") is True
            and result.get("hostname") == self.settings.turnstile_expected_hostname
            and result.get("action") == action
        ):
            raise AppError("TURNSTILE_INVALID", "Human verification failed.", status_code=400)
