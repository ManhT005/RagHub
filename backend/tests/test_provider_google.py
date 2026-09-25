from app.modules.ai_providers.adapters.google_gemini import (
    GoogleGeminiChatProvider,
    GoogleGeminiEmbeddingProvider,
)


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
