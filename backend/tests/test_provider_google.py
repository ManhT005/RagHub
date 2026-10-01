from app.modules.ai_providers.adapters.google_gemini import (
    GoogleGeminiChatProvider,
    GoogleGeminiEmbeddingProvider,
)
from app.modules.ai_providers.registry import ProviderRegistry


def test_gemini_uses_system_key_when_provider_has_no_private_key(monkeypatch) -> None:
    class Settings:
        gemini_api_key = "system-key"

    monkeypatch.setattr("app.modules.ai_providers.registry.get_settings", lambda: Settings())
    assert ProviderRegistry._gemini_secret(None) == "system-key"


def test_gemini_adapters_expose_normalized_provider_identity() -> None:
    chat = GoogleGeminiChatProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-chat",
        secret="secret",
    )
    embedding = GoogleGeminiEmbeddingProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-embedding",
        dimension=768,
        secret="secret",
    )

    assert chat.provider_name == "GOOGLE_GEMINI"
    assert embedding.metadata.provider_name == "GOOGLE_GEMINI"
    assert embedding.metadata.dimension == 768
