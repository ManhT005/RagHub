"""Bounded, credential-safe model discovery. No upstream bodies leave the host."""

import httpx
from raghub_core.domain.errors import CoreError

from app.core.exceptions import AppError
from app.modules.ai_providers.catalog import connection_catalog_id, supported_catalog_by_id
from app.modules.ai_providers.control_schemas import DiscoveredModel
from app.modules.ai_providers.schemas import validate_connection_endpoint


async def discover_native(connection, secret, base, transport):
    from app.modules.ai_providers.adapters.http import ProviderHttp

    item = supported_catalog_by_id(connection_catalog_id(connection))
    if item.discovery_profile == "CURATED":
        return [DiscoveredModel(**model.model_dump()) for model in item.presets]
    client = ProviderHttp(
        base_url=base, secret=secret, provider_name=connection.provider_type, transport=transport
    )
    try:
        if connection.provider_type == "CLOUDFLARE_WORKERS_AI":
            data = await client.request("/models/search", method="GET", params={"per_page": 1000})
            if not isinstance(data, dict) or data.get("success") is False:
                raise ValueError("Invalid catalog")
            models = []
            for row in data.get("result", []):
                task = (row.get("task") or {}).get("name", "")
                name = row.get("name", "")
                capability = {"Text Generation": "CHAT", "Text Embeddings": "EMBEDDING"}.get(task)
                if name == "@cf/baai/bge-reranker-base":
                    capability = "RERANK"
                if capability and isinstance(name, str) and 0 < len(name) <= 255:
                    models.append(DiscoveredModel(model=name, capabilities=[capability]))
            return models
        # The Hub catalog is public; authenticate the token independently.
        hub = ProviderHttp(
            base_url="https://huggingface.co",
            secret=secret,
            provider_name=connection.provider_type,
            transport=transport,
        )
        await hub.request("/api/whoami-v2", method="GET")
        chats = await client.request("/v1/models", method="GET")
        models = [
            DiscoveredModel(model=row["id"], capabilities=["CHAT"])
            for row in chats.get("data", [])
            if isinstance(row.get("id"), str)
        ]
        embeddings = await hub.request(
            "/api/models",
            method="GET",
            params={
                "inference_provider": "hf-inference",
                "pipeline_tag": "feature-extraction",
                "limit": 100,
                "expand": "inferenceProviderMapping",
            },
        )
        for row in embeddings:
            mapping = (row.get("inferenceProviderMapping") or {}).get("hf-inference", {})
            if mapping.get("status") == "live" and mapping.get("task") == "feature-extraction":
                name = row.get("id")
                if isinstance(name, str) and 0 < len(name) <= 255:
                    models.append(DiscoveredModel(model=name, capabilities=["EMBEDDING"]))
        return models
    except CoreError as exc:
        raise AppError(exc.code, "Provider catalog request failed.", status_code=422) from exc
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise AppError(
            "PROVIDER_INVALID_RESPONSE", "Invalid provider catalog.", status_code=422
        ) from exc


async def discover_models(
    connection, secret: str | None, *, transport=None
) -> list[DiscoveredModel]:
    provider_type = connection.provider_type
    if provider_type == "LOCAL_SENTENCE_TRANSFORMER":
        raise AppError("MODEL_DISCOVERY_UNSUPPORTED", "Enter a model ID manually.", status_code=409)
    try:
        base = validate_connection_endpoint(connection).rstrip("/")
    except ValueError as exc:
        raise AppError(
            "PROVIDER_ENDPOINT_REJECTED", "Provider endpoint is not allowed.", status_code=422
        ) from exc
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    catalog = supported_catalog_by_id(connection_catalog_id(connection))
    if provider_type in {"VOYAGE", "CLOUDFLARE_WORKERS_AI", "HUGGINGFACE_INFERENCE"}:
        return await discover_native(connection, secret, base, transport)
    if provider_type == "GOOGLE_GEMINI":
        # Native metadata is adjacent to the OpenAI-compatible runtime endpoint.
        base = base.removesuffix("/openai")
        url, key = f"{base}/models", "models"
        headers = {"x-goog-api-key": secret} if secret else {}
    elif provider_type == "OLLAMA":
        url, key = f"{base}/api/tags", "models"
    else:
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
                    elif len(catalog.capabilities) == 1:
                        capabilities = catalog.capabilities
                    elif catalog.id == "siliconflow":
                        capability = {
                            "chat": "CHAT",
                            "embedding": "EMBEDDING",
                            "rerank": "RERANK",
                        }.get(item.get("type"))
                        capabilities = [capability] if capability else []
                    if name in {"embedding-001", "text-embedding-004"}:
                        continue
                    preset = next((p for p in catalog.presets if p.model == name), None)
                    pricing = item.get("pricing") or {}
                    free = None
                    if catalog.id == "openrouter" and pricing:
                        free = all(str(pricing.get(k)) == "0" for k in ("prompt", "completion"))
                    # OpenAI-compatible /models does not advertise capability or dimension.
                    models.append(
                        DiscoveredModel(
                            model=name,
                            display_name=item.get("displayName"),
                            capabilities=capabilities,
                            size_bytes=item.get("size") if provider_type == "OLLAMA" else None,
                            context_tokens=item.get("context_length"),
                            free=free,
                            reasoning="reasoning" in item.get("supported_parameters", [])
                            if catalog.id == "openrouter"
                            else None,
                            dimension=preset.dimension if preset else None,
                            output_dimensions=preset.output_dimensions if preset else [],
                            recommended=preset.recommended if preset else False,
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
