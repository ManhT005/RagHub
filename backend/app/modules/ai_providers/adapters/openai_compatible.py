import asyncio
import json
import time
from collections.abc import AsyncIterator

import httpx
from raghub_core.domain.providers.contracts import (
    ChatMessage,
    ChatOptions,
    ChatStreamDelta,
    ChatUsage,
    EmbeddingMetadata,
)
from raghub_core.domain.providers.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderInvalidResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from raghub_core.domain.providers.usage import estimate_chat_usage

from app.modules.ai_providers.policy import ProviderRequestPolicy
from app.modules.ai_providers.request_profiles import embedding_payload
from app.modules.ai_providers.schemas import (
    validate_public_provider_url,
    validate_trusted_local_provider_url,
)


def _retry_after_seconds(response: httpx.Response) -> float:
    """Honor Retry-After on 429; fall back to 0 (caller uses backoff)."""
    try:
        value = float((response.headers.get("retry-after") or "").strip())
    except (ValueError, AttributeError):
        return 0.0
    return min(60.0, max(0.0, value))


class _OpenAICompatibleBase:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        secret: str | None,
        provider_name: str = "OPENAI_COMPATIBLE",
        policy: ProviderRequestPolicy | None = None,
        endpoint_scope: str = "PUBLIC",
        static_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.secret = secret
        self.provider_name = provider_name
        self.policy = policy or ProviderRequestPolicy()
        self.endpoint_scope = endpoint_scope
        self.static_headers = static_headers or {}

    def _validate_endpoint(self):
        try:
            if self.endpoint_scope == "LOCAL_TRUSTED":
                validate_trusted_local_provider_url(self.base_url)
            else:
                validate_public_provider_url(self.base_url)
        except ValueError as exc:
            raise ProviderConfigurationError("Provider endpoint is not allowed.") from exc

    def _headers(self) -> dict[str, str]:
        return {
            **self.static_headers,
            **({"Authorization": f"Bearer {self.secret}"} if self.secret else {}),
        }

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.policy.connect_timeout,
            read=self.policy.read_timeout,
            write=self.policy.read_timeout,
            pool=self.policy.connect_timeout,
        )

    @staticmethod
    def _response_error(status: int, headers=None) -> Exception:
        from app.modules.ai_providers.adapters.http import response_error

        return response_error(status, headers)


class OpenAICompatibleEmbeddingProvider(_OpenAICompatibleBase):
    batch_stride = 64

    def __init__(
        self,
        *,
        dimension: int,
        request_profile: str = "OPENAI_STANDARD",
        batch_limit: int = 64,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.metadata = EmbeddingMetadata(self.provider_name, self.model, dimension)
        self.request_profile = request_profile
        self.batch_limit = max(1, min(batch_limit, 1000))

    async def _embed(self, texts: list[str], input_type: str = "passage") -> list[list[float]]:
        from app.modules.ai_providers.adapters.http import record_request

        started, code = time.monotonic(), "OK"
        try:
            return await self._embed_request(texts, input_type)
        except ProviderError as exc:
            code = exc.code
            raise
        finally:
            record_request(self.provider_name, code, started)

    async def _embed_request(self, texts, input_type):
        self._validate_endpoint()
        payload = embedding_payload(self.request_profile, self.model, texts, input_type)
        last_error: Exception | None = None
        for attempt in range(self.policy.max_attempts):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout(), follow_redirects=False
                ) as client:
                    response = await client.post(
                        f"{self.base_url}/embeddings", headers=self._headers(), json=payload
                    )
                if not 200 <= response.status_code < 300:
                    error = self._response_error(
                        response.status_code, getattr(response, "headers", {})
                    )
                    if response.status_code not in {429, 502, 503, 504}:
                        raise error
                    last_error = error
                else:
                    data = response.json().get("data", [])
                    indices = [item["index"] for item in data]
                    if any(type(index) is not int for index in indices) or set(indices) != set(
                        range(len(texts))
                    ):
                        raise ProviderInvalidResponseError("Embedding indices are invalid.")
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
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise ProviderInvalidResponseError() from exc
            if attempt + 1 < self.policy.max_attempts:
                retry_after = getattr(last_error, "details", {}).get("retry_after_seconds", 0)
                await asyncio.sleep(max(retry_after, self.policy.backoff_seconds * (2**attempt)))
        assert last_error is not None
        raise last_error

    def _validate(self, vectors: object, expected: int) -> None:
        from app.modules.ai_providers.adapters.http import validate_vectors

        validate_vectors(vectors, expected, self.metadata.dimension)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        stride = min(self.batch_limit, max(1, getattr(self, "batch_stride", self.batch_limit)))
        for start in range(0, len(texts), stride):
            vectors.extend(await self._embed(texts[start : start + stride]))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "query"))[0]


class OpenAICompatibleChatProvider(_OpenAICompatibleBase):
    def __init__(self, *, include_stream_usage: bool = True, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.include_stream_usage = include_stream_usage

    async def stream_chat(
        self, messages: list[ChatMessage], options: ChatOptions
    ) -> AsyncIterator[ChatStreamDelta]:
        from app.modules.ai_providers.adapters.http import record_request

        started, code = time.monotonic(), "OK"
        stream = self._stream_chat(messages, options)
        try:
            async for delta in stream:
                yield delta
        except ProviderError as exc:
            code = exc.code
            raise
        finally:
            await stream.aclose()
            record_request(self.provider_name, code, started)

    async def _stream_chat(self, messages, options):
        self._validate_endpoint()
        payload: dict[str, object] = {
            "model": options.model or self.model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
            "stream": True,
        }
        if self.include_stream_usage:
            payload["stream_options"] = {"include_usage": True}
        for key in ("temperature", "max_tokens", "top_p", "stop"):
            value = getattr(options, key)
            if value is not None:
                payload[key] = value
        for attempt in range(self.policy.max_attempts):
            emitted = False
            completion: list[str] = []
            usage_received = False
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout(), follow_redirects=False
                ) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    ) as response:
                        if not 200 <= response.status_code < 300:
                            error = self._response_error(
                                response.status_code, getattr(response, "headers", {})
                            )
                            if response.status_code not in {429, 502, 503, 504}:
                                raise error
                            raise error
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                raw_usage = chunk.get("usage")
                                if raw_usage:
                                    usage = ChatUsage(
                                        prompt_tokens=int(raw_usage["prompt_tokens"]),
                                        completion_tokens=int(raw_usage["completion_tokens"]),
                                        total_tokens=int(raw_usage["total_tokens"]),
                                        source="provider",
                                    )
                                    usage_received = True
                                    yield ChatStreamDelta(usage=usage)
                                choices = chunk.get("choices") or []
                                token = choices[0]["delta"].get("content") if choices else None
                            except (
                                KeyError,
                                IndexError,
                                TypeError,
                                ValueError,
                                json.JSONDecodeError,
                            ):
                                continue
                            if token:
                                emitted = True
                                completion.append(token)
                                yield ChatStreamDelta(text=token)
                        if not emitted:
                            raise ProviderInvalidResponseError(
                                "The AI provider returned an empty chat stream."
                            )
                        if not usage_received:
                            yield ChatStreamDelta(
                                usage=estimate_chat_usage(messages, "".join(completion))
                            )
                return
            except (ProviderAuthenticationError, ProviderInvalidResponseError):
                raise
            except ProviderConfigurationError:
                raise
            except (httpx.TimeoutException, ProviderTimeoutError) as exc:
                error: Exception = ProviderTimeoutError()
                error.__cause__ = exc
            except (httpx.HTTPError, ProviderError) as exc:  # type: ignore[name-defined]
                error = exc if isinstance(exc, ProviderError) else ProviderUnavailableError()
            if emitted or attempt + 1 >= self.policy.max_attempts:
                raise error
            retry_after = getattr(error, "details", {}).get("retry_after_seconds", 0)
            await asyncio.sleep(max(retry_after, self.policy.backoff_seconds * (2**attempt)))
