import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError


class GeminiChatProvider:
    """Minimal Gemini adapter for its official OpenAI-compatible streaming endpoint."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def stream_chat(
        self, *, messages: list[dict[str, str]], model: str
    ) -> AsyncIterator[str]:
        if not self.settings.gemini_api_key:
            raise AppError(
                "CHAT_PROVIDER_NOT_CONFIGURED", "Gemini is not configured.", status_code=503
            )
        headers = {"Authorization": f"Bearer {self.settings.gemini_api_key}"}
        payload = {"model": model, "messages": messages, "stream": True}
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.chat_provider_timeout_seconds
            ) as client:
                async with client.stream(
                    "POST",
                    self.settings.gemini_base_url.rstrip("/") + "/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        raise AppError(
                            "CHAT_PROVIDER_UNAVAILABLE", "Gemini is unavailable.", status_code=502
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            return
                        try:
                            choice = json.loads(data)["choices"][0]
                            token = choice.get("delta", {}).get("content")
                        except (KeyError, IndexError, json.JSONDecodeError, TypeError):
                            continue
                        if token:
                            yield token
        except httpx.TimeoutException as exc:
            raise AppError("CHAT_PROVIDER_TIMEOUT", "Gemini timed out.", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                "CHAT_PROVIDER_UNAVAILABLE", "Gemini is unavailable.", status_code=502
            ) from exc
