from collections.abc import AsyncIterator

from app.core.config import Settings, get_settings
from app.modules.ai_providers.adapters.google_gemini import GoogleGeminiChatProvider
from app.modules.ai_providers.contracts import ChatMessage, ChatOptions
from app.modules.ai_providers.errors import ProviderConfigurationError
from app.modules.ai_providers.policy import ProviderRequestPolicy


class GeminiChatProvider:
    """Deprecated compatibility wrapper. Runtime code uses ProviderResolver."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def stream_chat(
        self, *, messages: list[dict[str, str]], model: str
    ) -> AsyncIterator[str]:
        if not self.settings.gemini_api_key:
            raise ProviderConfigurationError(
                "Gemini is not configured.", code="CHAT_PROVIDER_NOT_CONFIGURED", status_code=503
            )
        provider = GoogleGeminiChatProvider(
            base_url=self.settings.gemini_base_url,
            model=model,
            secret=self.settings.gemini_api_key,
            policy=ProviderRequestPolicy(read_timeout=self.settings.chat_provider_timeout_seconds),
        )
        normalized = [ChatMessage(**message) for message in messages]
        async for token in provider.stream_chat(normalized, ChatOptions(model=model)):
            yield token
