"""Bounded, credential-safe model discovery. No upstream bodies leave the host."""

import httpx

from app.core.exceptions import AppError
from app.modules.ai_providers.control_schemas import DiscoveredModel
from app.modules.ai_providers.schemas import validate_public_provider_url


async def discover_models(
    connection, secret: str | None, *, transport=None
) -> list[DiscoveredModel]:
    provider_type = connection.provider_type
    if provider_type == "LOCAL_SENTENCE_TRANSFORMER":
        raise AppError("MODEL_DISCOVERY_UNSUPPORTED", "Enter a model ID manually.", status_code=409)
    base = connection.base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    if provider_type == "GOOGLE_GEMINI":
        validate_public_provider_url(base)
        # Native metadata is adjacent to the OpenAI-compatible runtime endpoint.
        base = base.removesuffix("/openai")
        url, key = f"{base}/models", "models"
        headers = {"x-goog-api-key": secret} if secret else {}
    elif provider_type == "OLLAMA":
        url, key = f"{base}/api/tags", "models"
    else:
        validate_public_provider_url(base)
        url, key = f"{base}/models", "data"
    models: list[DiscoveredModel] = []
    params = {"pageSize": "1000"} if provider_type == "GOOGLE_GEMINI" else {}
    try:
        async with httpx.AsyncClient(
            timeout=15, follow_redirects=False, transport=transport
        ) as client:
            for _ in range(10):
                response = await client.get(url, headers=headers, params=params)
                if response.status_code in {401, 403}:
                    raise AppError(
                        "PROVIDER_AUTH_FAILED", "Provider authentication failed.", status_code=422
                    )
                if response.status_code in {404, 405, 501}:
                    raise AppError(
                        "MODEL_DISCOVERY_UNSUPPORTED", "Enter a model ID manually.", status_code=409
                    )
                if response.status_code != 200 or len(response.content) > 2_000_000:
                    raise AppError(
                        "PROVIDER_UNREACHABLE", "Provider could not be reached.", status_code=422
                    )
                data = response.json()
                for item in data.get(key, []):
                    name = item.get("id") or item.get("name") or item.get("model")
                    if not isinstance(name, str) or not name or len(name) > 255:
                        continue
                    capabilities = []
                    if provider_type == "GOOGLE_GEMINI":
                        methods = item.get("supportedGenerationMethods", [])
                        if "generateContent" in methods:
                            capabilities.append("CHAT")
                        if "embedContent" in methods or "batchEmbedContents" in methods:
                            capabilities.append("EMBEDDING")
                        name = name.removeprefix("models/")
                    elif provider_type == "OLLAMA":
                        capabilities = ["CHAT"]
                    # OpenAI-compatible /models does not advertise capability or dimension.
                    models.append(
                        DiscoveredModel(
                            model=name,
                            display_name=item.get("displayName"),
                            capabilities=capabilities,
                        )
                    )
                token = data.get("nextPageToken")
                if provider_type != "GOOGLE_GEMINI" or not token:
                    break
                params["pageToken"] = token
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        raise AppError(
            "PROVIDER_UNREACHABLE", "Provider could not be reached.", status_code=422
        ) from exc
    return list({item.model: item for item in models}.values())
