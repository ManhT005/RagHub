from app.modules.ai_providers.adapters.openai_compatible import (
    OpenAICompatibleChatProvider,
    OpenAICompatibleEmbeddingProvider,
)


class GoogleGeminiEmbeddingProvider(OpenAICompatibleEmbeddingProvider):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(provider_name="GOOGLE_GEMINI", **kwargs)


class GoogleGeminiChatProvider(OpenAICompatibleChatProvider):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(provider_name="GOOGLE_GEMINI", **kwargs)
