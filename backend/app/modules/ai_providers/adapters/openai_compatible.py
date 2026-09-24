import asyncio
import json
import math
from collections.abc import AsyncIterator

import httpx

from app.modules.ai_providers.contracts import (
    ChatMessage,
    ChatOptions,
    EmbeddingMetadata,
)
from app.modules.ai_providers.errors import (
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.modules.ai_providers.policy import ProviderRequestPolicy


class _OpenAICompatibleBase:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        secret: str | None,
        provider_name: str = "OPENAI_COMPATIBLE",
        policy: ProviderRequestPolicy | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.secret = secret
        self.provider_name = provider_name
        self.policy = policy or ProviderRequestPolicy()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.secret}"} if self.secret else {}

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.policy.connect_timeout,
            read=self.policy.read_timeout,
            write=self.policy.read_timeout,
            pool=self.policy.connect_timeout,
        )

    @staticmethod
    def _response_error(status: int) -> Exception:
        if status in {401, 403}:
            return ProviderAuthenticationError()
        if status == 429:
            return ProviderRateLimitError()
        return ProviderUnavailableError()


class OpenAICompatibleEmbeddingProvider(_OpenAICompatibleBase):
    def __init__(self, *, dimension: int, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.metadata = EmbeddingMetadata(self.provider_name, self.model, dimension)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": texts}
        last_error: Exception | None = None
        for attempt in range(self.policy.max_attempts):
            try:
                async with httpx.AsyncClient(timeout=self._timeout()) as client:
                    response = await client.post(
                        f"{self.base_url}/embeddings", headers=self._headers(), json=payload
                    )
                if response.status_code >= 400:
                    error = self._response_error(response.status_code)
                    if response.status_code not in {429, 502, 503, 504}:
                        raise error
                    last_error = error
                else:
                    data = response.json().get("data", [])
                    ordered = sorted(data, key=lambda item: item.get("index", 0))
                    vectors = [item.get("embedding") for item in ordered]
                    self._validate(vectors, len(texts))
                    return vectors
            except httpx.TimeoutException as exc:
                last_error = ProviderTimeoutError()
                last_error.__cause__ = exc
            except httpx.HTTPError as exc:
                last_error = ProviderUnavailableError()
                last_error.__cause__ = exc
            except (ValueError, TypeError, KeyError) as exc:
                raise ProviderInvalidResponseError() from exc
            if attempt + 1 < self.policy.max_attempts:
                await asyncio.sleep(self.policy.backoff_seconds * (2**attempt))
        assert last_error is not None
        raise last_error

    def _validate(self, vectors: object, expected: int) -> None:
        if not isinstance(vectors, list) or len(vectors) != expected:
            raise ProviderInvalidResponseError("Embedding response count does not match input.")
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.metadata.dimension:
                raise ProviderInvalidResponseError("Embedding dimension does not match config.")
            valid = all(isinstance(value, int | float) and math.isfinite(value) for value in vector)
            if not valid:
                raise ProviderInvalidResponseError("Embedding contains a non-finite value.")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 64):
            vectors.extend(await self._embed(texts[start : start + 64]))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]


class OpenAICompatibleChatProvider(_OpenAICompatibleBase):
    async def stream_chat(
        self, messages: list[ChatMessage], options: ChatOptions
    ) -> AsyncIterator[str]:
        payload: dict[str, object] = {
            "model": options.model or self.model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
            "stream": True,
        }
        for key in ("temperature", "max_tokens", "top_p", "stop"):
            value = getattr(options, key)
            if value is not None:
                payload[key] = value
        for attempt in range(self.policy.max_attempts):
            emitted = False
            try:
                async with httpx.AsyncClient(timeout=self._timeout()) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    ) as response:
                        if response.status_code >= 400:
                            error = self._response_error(response.status_code)
                            if response.status_code not in {429, 502, 503, 504}:
                                raise error
                            raise error
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                return
                            try:
                                token = json.loads(data)["choices"][0]["delta"].get("content")
                            except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                                continue
                            if token:
                                emitted = True
                                yield token
                return
            except (ProviderAuthenticationError, ProviderInvalidResponseError):
                raise
            except (httpx.TimeoutException, ProviderTimeoutError) as exc:
                error: Exception = ProviderTimeoutError()
                error.__cause__ = exc
            except (httpx.HTTPError, ProviderError) as exc:  # type: ignore[name-defined]
                error = exc if isinstance(exc, ProviderError) else ProviderUnavailableError()
            if emitted or attempt + 1 >= self.policy.max_attempts:
                raise error
            await asyncio.sleep(self.policy.backoff_seconds * (2**attempt))


from app.modules.ai_providers.errors import ProviderError  # noqa: E402
