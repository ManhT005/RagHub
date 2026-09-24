import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from app.modules.ai_providers.contracts import ChatMessage, ChatOptions
from app.modules.ai_providers.errors import (
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.modules.ai_providers.policy import ProviderRequestPolicy


class OllamaChatProvider:
    provider_name = "OLLAMA"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        policy: ProviderRequestPolicy | None = None,
        config: dict[str, object] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.policy = policy or ProviderRequestPolicy(read_timeout=120)
        self.config = config or {}

    async def stream_chat(
        self, messages: list[ChatMessage], options: ChatOptions
    ) -> AsyncIterator[str]:
        provider_options = dict(self.config.get("options", {}))
        for key in ("temperature", "top_p", "stop"):
            value = getattr(options, key)
            if value is not None:
                provider_options[key] = value
        if options.max_tokens is not None:
            provider_options["num_predict"] = options.max_tokens
        payload = {
            "model": options.model or self.model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
            "stream": True,
            "options": provider_options,
        }
        timeout = httpx.Timeout(
            connect=self.policy.connect_timeout,
            read=self.policy.read_timeout,
            write=self.policy.read_timeout,
            pool=self.policy.connect_timeout,
        )
        for attempt in range(self.policy.max_attempts):
            emitted = False
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST", f"{self.base_url}/api/chat", json=payload
                    ) as response:
                        if response.status_code >= 400:
                            if response.status_code in {400, 404}:
                                raise ProviderInvalidResponseError(
                                    "Ollama rejected the request or model."
                                )
                            if response.status_code in {401, 403}:
                                raise ProviderAuthenticationError()
                            if response.status_code == 429:
                                raise ProviderRateLimitError()
                            raise ProviderUnavailableError()
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                token = data.get("message", {}).get("content")
                            except (TypeError, json.JSONDecodeError) as exc:
                                raise ProviderInvalidResponseError() from exc
                            if token:
                                emitted = True
                                yield token
                            if data.get("done"):
                                return
                return
            except httpx.TimeoutException as exc:
                error: Exception = ProviderTimeoutError()
                error.__cause__ = exc
            except httpx.HTTPError as exc:
                error = ProviderUnavailableError()
                error.__cause__ = exc
            except (ProviderUnavailableError, ProviderRateLimitError) as exc:
                error = exc
            if emitted or attempt + 1 >= self.policy.max_attempts:
                raise error
            await asyncio.sleep(self.policy.backoff_seconds * (2**attempt))
