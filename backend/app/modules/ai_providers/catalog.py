"""Production catalog describes only capabilities backed by runtime factories."""

from pydantic import BaseModel, Field

from app.core.exceptions import AppError


class ConnectionField(BaseModel):
    key: str
    label: str
    required: bool = False
    type: str = "text"


class CatalogModel(BaseModel):
    model: str
    capabilities: list[str]
    dimension: int | None = None
    output_dimensions: list[int] = Field(default_factory=list)
    deprecated: bool = False
    recommended: bool = True


class CatalogItem(BaseModel):
    id: str
    name: str
    category: str
    provider_type: str | None
    default_base_url: str | None = None
    capabilities: list[str]
    supports_model_discovery: bool = False
    auth_type: str = "API_KEY"
    docs_url: str | None = None
    api_key_url: str | None = None
    status: str = "SUPPORTED"
    endpoint_scope: str = "PUBLIC"
    discovery_profile: str = "OPENAI_MODELS"
    request_profile: str = "OPENAI_STANDARD"
    icon_key: str | None = None
    pricing_url: str | None = None
    access_tier: str | None = None
    free_tier_note: str | None = None
    last_verified_at: str = "2026-10-05"
    locked_base_url: bool = False
    fields: list[ConnectionField] = Field(default_factory=list)
    presets: list[CatalogModel] = Field(default_factory=list)
    migration_guidance: str | None = None


CATALOG = [
    CatalogItem(
        id="gemini",
        name="Google Gemini",
        category="Cloud",
        provider_type="GOOGLE_GEMINI",
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        capabilities=["CHAT", "EMBEDDING"],
        supports_model_discovery=True,
        docs_url="https://ai.google.dev/gemini-api/docs",
        api_key_url="https://aistudio.google.com/apikey",
        discovery_profile="GEMINI_MODELS",
        request_profile="GEMINI",
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        access_tier="FREE_ALLOCATION",
        presets=[
            CatalogModel(
                model=model,
                capabilities=["EMBEDDING"],
                dimension=3072,
                output_dimensions=[768, 1536, 3072],
            )
            for model in ("gemini-embedding-2", "gemini-embedding-001")
        ],
    ),
    CatalogItem(
        id="openai",
        name="OpenAI",
        category="Cloud",
        provider_type="OPENAI_COMPATIBLE",
        default_base_url="https://api.openai.com/v1",
        capabilities=["CHAT", "EMBEDDING"],
        supports_model_discovery=True,
    ),
    CatalogItem(
        id="compatible",
        name="OpenAI-compatible",
        category="Custom",
        provider_type="OPENAI_COMPATIBLE",
        capabilities=["CHAT", "EMBEDDING"],
        supports_model_discovery=True,
    ),
    CatalogItem(
        id="ollama",
        name="Ollama",
        category="Local",
        provider_type="OLLAMA",
        default_base_url="http://ollama:11434",
        capabilities=["CHAT"],
        supports_model_discovery=True,
        auth_type="NONE",
        docs_url="https://docs.ollama.com",
        endpoint_scope="LOCAL_TRUSTED",
        discovery_profile="OLLAMA",
        request_profile="OLLAMA",
    ),
    CatalogItem(
        id="sentence-transformer",
        name="Sentence Transformer",
        category="Local",
        provider_type="LOCAL_SENTENCE_TRANSFORMER",
        capabilities=["EMBEDDING"],
        auth_type="NONE",
        endpoint_scope="LOCAL_TRUSTED",
        discovery_profile="MANUAL",
        request_profile="SENTENCE_TRANSFORMER",
    ),
    CatalogItem(
        id="nvidia-nim",
        name="NVIDIA NIM",
        category="Cloud",
        provider_type="OPENAI_COMPATIBLE",
        default_base_url="https://integrate.api.nvidia.com/v1",
        capabilities=["CHAT", "EMBEDDING"],
        supports_model_discovery=True,
        request_profile="NVIDIA_NIM",
        docs_url="https://docs.api.nvidia.com/nim/",
        api_key_url="https://build.nvidia.com/",
    ),
    CatalogItem(
        id="9router",
        name="9Router",
        category="Local",
        provider_type="OPENAI_COMPATIBLE",
        default_base_url="http://9router:20128/v1",
        capabilities=["CHAT", "EMBEDDING"],
        supports_model_discovery=True,
        endpoint_scope="LOCAL_TRUSTED",
        auth_type="OPTIONAL_API_KEY",
    ),
    *[
        CatalogItem(
            id=brand,
            name=name,
            category="Cloud",
            provider_type="OPENAI_COMPATIBLE",
            default_base_url=base,
            capabilities=capabilities,
            supports_model_discovery=True,
            status="BETA",
            locked_base_url=True,
            request_profile=profile,
            access_tier=tier,
            docs_url=docs,
            pricing_url=pricing,
            api_key_url=key_url,
            free_tier_note="Quota and availability follow the provider's current policy.",
            fields=(
                [
                    ConnectionField(key="app_url", label="App URL", type="url"),
                    ConnectionField(key="app_name", label="App name"),
                ]
                if brand == "openrouter"
                else []
            ),
        )
        for brand, name, base, capabilities, profile, tier, docs, pricing, key_url in (
            (
                "groq",
                "GroqCloud",
                "https://api.groq.com/openai/v1",
                ["CHAT"],
                "GROQ",
                "FREE_ALLOCATION",
                "https://console.groq.com/docs",
                "https://groq.com/pricing",
                "https://console.groq.com/keys",
            ),
            (
                "openrouter",
                "OpenRouter",
                "https://openrouter.ai/api/v1",
                ["CHAT"],
                "OPENROUTER",
                "MIXED",
                "https://openrouter.ai/docs",
                "https://openrouter.ai/pricing",
                "https://openrouter.ai/settings/keys",
            ),
            (
                "cerebras",
                "Cerebras",
                "https://api.cerebras.ai/v1",
                ["CHAT"],
                "CEREBRAS",
                "FREE_TRIAL",
                "https://inference-docs.cerebras.ai",
                "https://inference-docs.cerebras.ai/support/pricing",
                "https://cloud.cerebras.ai",
            ),
            (
                "siliconflow",
                "SiliconFlow",
                "https://api.siliconflow.com/v1",
                ["CHAT", "EMBEDDING", "RERANK"],
                "SILICONFLOW",
                "MIXED",
                "https://docs.siliconflow.com",
                "https://www.siliconflow.com/pricing",
                "https://cloud.siliconflow.com",
            ),
        )
    ],
    CatalogItem(
        id="voyage",
        name="Voyage AI",
        category="Cloud",
        provider_type="VOYAGE",
        default_base_url="https://api.voyageai.com/v1",
        capabilities=["EMBEDDING", "RERANK"],
        supports_model_discovery=True,
        discovery_profile="CURATED",
        request_profile="VOYAGE",
        status="BETA",
        locked_base_url=True,
        access_tier="FREE_ALLOCATION",
        docs_url="https://docs.voyageai.com",
        pricing_url="https://docs.voyageai.com/docs/pricing",
        api_key_url="https://dashboard.voyageai.com",
        presets=[
            *[
                CatalogModel(
                    model=model,
                    capabilities=["EMBEDDING"],
                    dimension=1024,
                    output_dimensions=[256, 512, 1024, 2048],
                )
                for model in ("voyage-4", "voyage-4-lite", "voyage-4-large", "voyage-context-4")
            ],
            CatalogModel(
                model="voyage-multilingual-2",
                capabilities=["EMBEDDING"],
                dimension=1024,
                recommended=False,
            ),
            *[
                CatalogModel(model=model, capabilities=["RERANK"])
                for model in ("rerank-3", "rerank-3-lite")
            ],
        ],
    ),
    CatalogItem(
        id="cloudflare-workers-ai",
        name="Cloudflare Workers AI",
        icon_key="cloudflare",
        category="Cloud",
        provider_type="CLOUDFLARE_WORKERS_AI",
        capabilities=["CHAT", "EMBEDDING", "RERANK"],
        default_base_url="https://api.cloudflare.com/client/v4",
        request_profile="CLOUDFLARE",
        discovery_profile="CLOUDFLARE",
        supports_model_discovery=True,
        status="BETA",
        locked_base_url=True,
        access_tier="FREE_ALLOCATION",
        fields=[ConnectionField(key="account_id", label="Account ID", required=True)],
        docs_url="https://developers.cloudflare.com/workers-ai/",
        pricing_url="https://developers.cloudflare.com/workers-ai/platform/pricing/",
        api_key_url="https://dash.cloudflare.com/profile/api-tokens",
    ),
    CatalogItem(
        id="huggingface",
        name="Hugging Face Inference",
        category="Cloud",
        provider_type="HUGGINGFACE_INFERENCE",
        default_base_url="https://router.huggingface.co",
        capabilities=["CHAT", "EMBEDDING"],
        request_profile="HUGGINGFACE",
        discovery_profile="HUGGINGFACE",
        supports_model_discovery=True,
        status="BETA",
        locked_base_url=True,
        access_tier="FREE_TRIAL",
        docs_url="https://huggingface.co/docs/inference-providers",
        pricing_url="https://huggingface.co/docs/inference-providers/pricing",
        api_key_url="https://huggingface.co/settings/tokens",
    ),
    CatalogItem(
        id="github-models",
        name="GitHub Models",
        category="Cloud",
        provider_type=None,
        capabilities=[],
        status="RETIRED",
        access_tier="RETIRED",
        docs_url="https://docs.github.com/en/github-models",
        migration_guidance=(
            "Retired July 30, 2026. Create a new connection using another provider; "
            "existing records are preserved."
        ),
    ),
    *[
        CatalogItem(
            id=name.lower().replace(" ", "-"),
            name=name,
            category="Cloud",
            provider_type=None,
            capabilities=[],
            status="COMING_SOON",
        )
        for name in (
            "Anthropic",
            "Azure OpenAI",
            "DeepSeek",
        )
    ],
]


def supported_catalog(provider_type: str) -> CatalogItem:
    for item in CATALOG:
        if item.status in {"SUPPORTED", "BETA"} and item.provider_type == provider_type:
            return item
    raise AppError(
        "UNSUPPORTED_PROVIDER", "Provider has no supported runtime adapter.", status_code=422
    )


def supported_catalog_by_id(catalog_id: str) -> CatalogItem:
    for item in CATALOG:
        if item.id == catalog_id and item.status in {"SUPPORTED", "BETA"}:
            return item
    raise AppError("UNSUPPORTED_PROVIDER", "Provider catalog item is unavailable.", status_code=422)


def resolve_legacy_catalog_id(provider_type: str, base_url: str | None) -> str | None:
    if provider_type == "OPENAI_COMPATIBLE":
        return (
            "openai"
            if (base_url or "").rstrip("/") == "https://api.openai.com/v1"
            else "compatible"
        )
    return {
        "GOOGLE_GEMINI": "gemini",
        "OLLAMA": "ollama",
        "LOCAL_SENTENCE_TRANSFORMER": "sentence-transformer",
        "VOYAGE": "voyage",
        "CLOUDFLARE_WORKERS_AI": "cloudflare-workers-ai",
        "HUGGINGFACE_INFERENCE": "huggingface",
    }.get(provider_type)


def connection_catalog_id(connection) -> str | None:
    return getattr(connection, "catalog_id", None) or resolve_legacy_catalog_id(
        connection.provider_type, connection.base_url
    )
