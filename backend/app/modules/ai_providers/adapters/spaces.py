"""Explicit Gradio queue mappings; no remote code execution or implicit role guessing."""

import asyncio
import json
import re

import httpx
from raghub_core.domain.providers.contracts import ChatStreamDelta, EmbeddingMetadata
from raghub_core.domain.providers.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

from app.modules.ai_providers.adapters.http import response_error, validate_vectors
from app.modules.ai_providers.schemas import validate_public_provider_url


def space_origin(value):
    value = (value or "").rstrip("/")
    if re.fullmatch(r"https://[a-zA-Z0-9-]+\.hf\.space", value):
        return validate_public_provider_url(value)
    if re.fullmatch(r"https://huggingface\.co/spaces/[\w.-]+/[\w.-]+", value):
        return value
    raise ValueError("Use an HTTPS hf.space origin or huggingface.co/spaces/owner/name URL.")


def mapping(options, key):
    raw = options.get(key)
    try:
        result = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(result, dict) or not re.fullmatch(r"[\w-]+", result.get("api", "")):
            raise ValueError
        if not isinstance(result.get("inputs"), list):
            raise ValueError
        if not isinstance(result.get("output", "0"), str):
            raise ValueError
        return result
    except (ValueError, TypeError) as exc:
        raise ProviderConfigurationError(f"Configure a valid {key} endpoint mapping.") from exc


def substitute(value, variables):
    if isinstance(value, str) and value.startswith("$"):
        if value not in variables:
            raise ProviderConfigurationError("Unsupported Space input placeholder.")
        return variables[value]
    if isinstance(value, list):
        return [substitute(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item, variables) for key, item in value.items()}
    return value


def extract(value, path):
    try:
        for part in path.split(".") if path else []:
            value = value[int(part)] if isinstance(value, list) else value[part]
        return value
    except (KeyError, ValueError, IndexError, TypeError) as exc:
        raise ProviderInvalidResponseError(
            "Space output does not match the configured path."
        ) from exc


def check_space_result(value):
    """Gradio can return HTTP 200/complete containing an application error."""
    if isinstance(value, list):
        for item in value:
            check_space_result(item)
    elif isinstance(value, dict) and (value.get("status") == "error" or value.get("error_code")):
        message = str(value.get("message", "")).lower()
        code = str(value.get("error_code", "")).upper()
        if any(word in message for word in ("quota", "runs limit", "gpu limit", "rate limit")):
            raise ProviderRateLimitError(
                "Space GPU quota exhausted. Check the HF account quota/token."
            )
        if code in {"UNAUTHORIZED", "AUTH_FAILED", "INVALID_TOKEN"} or any(
            word in message for word in ("invalid token", "unauthorized", "authentication failed")
        ):
            raise ProviderAuthenticationError()
        raise ProviderInvalidResponseError(
            "Space inference failed; no embedding vector was returned."
        )


class SpaceClient:
    def __init__(self, base_url, secret=None, transport=None):
        self.base_url = space_origin(base_url)
        self.headers = {"Authorization": f"Bearer {secret}"} if secret else {}
        self.transport = transport

    async def origin(self, client):
        if self.base_url.startswith("https://huggingface.co/spaces/"):
            repo = self.base_url.split("/spaces/", 1)[1]
            response = await client.get(
                f"https://huggingface.co/api/spaces/{repo}", headers=self.headers
            )
            self.check(response)
            host = space_origin(response.json().get("host"))
            if not host.endswith(".hf.space"):
                raise ProviderConfigurationError("Invalid Space host metadata.")
            return host
        return self.base_url

    @staticmethod
    def check(response):
        if response.status_code != 200:
            raise response_error(response.status_code, response.headers)

    def client(self):
        return httpx.AsyncClient(timeout=180, follow_redirects=False, transport=self.transport)

    async def inspect(self):
        try:
            async with asyncio.timeout(30), self.client() as client:
                base = await self.origin(client)
                response = await client.get(f"{base}/gradio_api/info", headers=self.headers)
                self.check(response)
                if len(response.content) > 2_000_000:
                    raise ValueError
                named = response.json().get("named_endpoints")
                if not isinstance(named, dict):
                    raise ValueError
                return {
                    "base_url": base,
                    "endpoints": [
                        {
                            "name": name.lstrip("/"),
                            "parameters": data.get("parameters", []),
                            "returns": data.get("returns", []),
                        }
                        for name, data in list(named.items())[:100]
                    ],
                }
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProviderTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError() from exc
        except (ValueError, TypeError, AttributeError) as exc:
            raise ProviderInvalidResponseError(
                "Space must expose a modern Gradio named API."
            ) from exc

    async def call(self, spec, variables):
        try:
            async with asyncio.timeout(180), self.client() as client:
                base = await self.origin(client)
                url = f"{base}/gradio_api/call/{spec['api']}"
                response = await client.post(
                    url, headers=self.headers, json={"data": substitute(spec["inputs"], variables)}
                )
                self.check(response)
                identifier = response.json().get("event_id", "")
                if not isinstance(identifier, str) or not re.fullmatch(r"[\w-]+", identifier):
                    raise ValueError
                async with client.stream(
                    "GET", f"{url}/{identifier}", headers=self.headers
                ) as result:
                    self.check(result)
                    event, size = "", 0
                    async for line in result.aiter_lines():
                        size += len(line)
                        if size > 16_000_000:
                            raise ValueError
                        if line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:"):
                            if event == "error":
                                payload = json.loads(line[5:])
                                check_space_result(payload)
                                if isinstance(payload, str):
                                    check_space_result({"status": "error", "message": payload})
                                raise ProviderInvalidResponseError(
                                    "Space failed; check quota or endpoint mapping."
                                )
                            if event == "complete":
                                payload = json.loads(line[5:])
                                check_space_result(payload)
                                return extract(payload, spec.get("output", "0"))
                raise ValueError
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProviderTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError() from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise ProviderInvalidResponseError(
                "Invalid or incomplete Space queue response."
            ) from exc


class SpacesEmbeddingProvider:
    def __init__(self, *, base_url, secret, model, dimension, options):
        self.client = SpaceClient(base_url, secret)
        self.options = options
        self.metadata = EmbeddingMetadata("HUGGINGFACE_SPACES", model, dimension)

    async def _embed(self, texts, query):
        spec = mapping(self.options, "spaces_query" if query else "spaces_document")
        vectors = []
        # Single-input endpoints remain usable; batching can be expressed with $texts.
        for text in texts:
            output = await self.client.call(
                spec,
                {
                    "$text": text,
                    "$texts": [text],
                    "$dimension": self.metadata.dimension,
                    "$task": "query" if query else "document",
                },
            )
            if isinstance(output, list) and output and isinstance(output[0], int | float):
                output = [output]
            vectors.extend(validate_vectors(output, 1, self.metadata.dimension))
        return vectors

    async def embed_query(self, text):
        return (await self._embed([text], True))[0]

    async def embed_documents(self, texts):
        return await self._embed(texts, False)


class SpacesChatProvider:
    provider_name = "HUGGINGFACE_SPACES"

    def __init__(self, *, base_url, secret, model, options):
        self.client, self.model, self.options = SpaceClient(base_url, secret), model, options

    async def stream_chat(self, messages, options):
        spec = mapping(self.options, "spaces_chat")
        output = await self.client.call(
            spec,
            {
                "$prompt": "\n\n".join(f"{item.role}: {item.content}" for item in messages),
                "$messages": [{"role": item.role, "content": item.content} for item in messages],
            },
        )
        if not isinstance(output, str):
            raise ProviderInvalidResponseError("Configure a Space output path selecting text.")
        yield ChatStreamDelta(text=output)
