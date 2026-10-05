"""Production catalog describes only capabilities backed by runtime factories."""

from pydantic import BaseModel

from app.core.exceptions import AppError


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
            "Groq",
            "Cloudflare",
        )
    ],
]


def supported_catalog(provider_type: str) -> CatalogItem:
    for item in CATALOG:
        if item.status == "SUPPORTED" and item.provider_type == provider_type:
            return item
    raise AppError(
        "UNSUPPORTED_PROVIDER", "Provider has no supported runtime adapter.", status_code=422
    )


def supported_catalog_by_id(catalog_id: str) -> CatalogItem:
    for item in CATALOG:
        if item.id == catalog_id and item.status == "SUPPORTED":
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
    }.get(provider_type)


def connection_catalog_id(connection) -> str | None:
    return getattr(connection, "catalog_id", None) or resolve_legacy_catalog_id(
        connection.provider_type, connection.base_url
    )
