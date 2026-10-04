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
    ),
    CatalogItem(
        id="sentence-transformer",
        name="Sentence Transformer",
        category="Local",
        provider_type="LOCAL_SENTENCE_TRANSFORMER",
        capabilities=["EMBEDDING"],
        auth_type="NONE",
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
            "NVIDIA",
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
