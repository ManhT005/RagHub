"""Shared bounded JSON transport and validation for host provider adapters."""

import asyncio
import logging
import math
import time
from collections import Counter

import httpx
from raghub_core.domain.providers.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

from app.modules.ai_providers.policy import ProviderRequestPolicy
from app.modules.ai_providers.schemas import validate_public_provider_url

logger = logging.getLogger(__name__)
REQUESTS = Counter()


def record_request(provider, code, started):
    REQUESTS[(provider, code)] += 1
    logger.info(
        "provider_request provider=%s status=%s latency_ms=%d",
        provider,
        code,
        (time.monotonic() - started) * 1000,
    )


def response_error(status, headers=None):
    if status in {401, 403}:
        return ProviderAuthenticationError()
    if status == 429:
        error = ProviderRateLimitError()
        try:
            seconds = float((headers or {}).get("Retry-After", 0))
            if math.isfinite(seconds):
                error.details["retry_after_seconds"] = min(120, max(0, seconds))
        except (ValueError, TypeError):
            pass
        return error
    if status == 404:
        return ProviderConfigurationError(
            "Provider model was not found.", code="PROVIDER_MODEL_NOT_FOUND"
        )
    if 400 <= status < 500 or 300 <= status < 400:
        return ProviderInvalidResponseError("The provider rejected this request.")
    return ProviderUnavailableError()


def validate_vectors(vectors, count, dimension=None):
    if not isinstance(vectors, list) or len(vectors) != count or not vectors:
        raise ProviderInvalidResponseError("Embedding response count does not match input.")
    size = dimension or (len(vectors[0]) if isinstance(vectors[0], list) else 0)
    if not 1 <= size <= 65536:
        raise ProviderInvalidResponseError("Embedding dimension is invalid.")
    for vector in vectors:
        if (
            not isinstance(vector, list)
            or len(vector) != size
            or not all(
                isinstance(value, int | float)
                and not isinstance(value, bool)
                and math.isfinite(value)
                for value in vector
            )
        ):
            raise ProviderInvalidResponseError("Embedding contains invalid values or dimensions.")
    return vectors


class ProviderHttp:
    def __init__(
        self, *, base_url, secret, provider_name, policy=None, transport=None, native_google=False
    ):
        self.base_url = base_url.rstrip("/")
        self.secret, self.provider_name = secret, provider_name
        self.policy = policy or ProviderRequestPolicy()
        self.transport = transport
        self.native_google = native_google

    async def request(self, path, payload=None, *, method="POST", params=None):
        try:
            validate_public_provider_url(self.base_url)
        except ValueError as exc:
            raise ProviderConfigurationError("Provider endpoint is not allowed.") from exc
        headers = {"Authorization": f"Bearer {self.secret}"} if self.secret else {}
        if self.native_google:
            headers = {"x-goog-api-key": self.secret} if self.secret else {}
        started = time.monotonic()
        code = "OK"
        try:
            for attempt in range(self.policy.max_attempts):
                try:
                    async with httpx.AsyncClient(
                        timeout=httpx.Timeout(
                            self.policy.read_timeout, connect=self.policy.connect_timeout
                        ),
                        follow_redirects=False,
                        transport=self.transport,
                    ) as client:
                        response = await client.request(
                            method,
                            self.base_url + path,
                            json=payload,
                            headers=headers,
                            params=params,
                        )
                    if not 200 <= response.status_code < 300:
                        error = response_error(response.status_code, response.headers)
                        if response.status_code not in {429, 502, 503, 504}:
                            raise error
                    else:
                        if len(response.content) > 32_000_000:
                            raise ProviderInvalidResponseError()
                        try:
                            return response.json()
                        except ValueError as exc:
                            raise ProviderInvalidResponseError() from exc
                except httpx.TimeoutException:
                    error = ProviderTimeoutError()
                except httpx.HTTPError:
                    error = ProviderUnavailableError()
                if attempt + 1 >= self.policy.max_attempts:
                    raise error
                retry_after = getattr(error, "details", {}).get("retry_after_seconds", 0)
                await asyncio.sleep(max(retry_after, self.policy.backoff_seconds * 2**attempt))
        except ProviderError as exc:
            code = exc.code
            raise
        finally:
            record_request(self.provider_name, code, started)
