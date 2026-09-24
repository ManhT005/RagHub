from collections.abc import Callable

from app.modules.ai_providers.adapters import (
    GoogleGeminiChatProvider,
    GoogleGeminiEmbeddingProvider,
    LocalSentenceTransformerProvider,
    OllamaChatProvider,
    OpenAICompatibleChatProvider,
    OpenAICompatibleEmbeddingProvider,
)
from app.modules.ai_providers.contracts import ChatProvider, EmbeddingProvider
from app.modules.ai_providers.enums import ProviderCapability, ProviderType
from app.modules.ai_providers.errors import ProviderConfigurationError
from app.modules.ai_providers.models import ProviderConfig
from app.modules.ai_providers.policy import ProviderRequestPolicy

ProviderFactory = Callable[[ProviderConfig, str | None], object]


class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[tuple[str, str], ProviderFactory] = {}
        self.register(
            ProviderType.OPENAI_COMPATIBLE,
            ProviderCapability.EMBEDDING,
            self._openai_embedding,
        )
        self.register(ProviderType.OPENAI_COMPATIBLE, ProviderCapability.CHAT, self._openai_chat)
        self.register(
            ProviderType.GOOGLE_GEMINI,
            ProviderCapability.EMBEDDING,
            self._gemini_embedding,
        )
        self.register(ProviderType.GOOGLE_GEMINI, ProviderCapability.CHAT, self._gemini_chat)
        self.register(
            ProviderType.LOCAL_SENTENCE_TRANSFORMER,
            ProviderCapability.EMBEDDING,
            self._local_embedding,
        )
        self.register(ProviderType.OLLAMA, ProviderCapability.CHAT, self._ollama_chat)

    def register(
        self, provider_type: ProviderType, capability: ProviderCapability, factory: ProviderFactory
    ) -> None:
        self._factories[(provider_type, capability)] = factory

    def create(self, config: ProviderConfig, secret: str | None) -> object:
        factory = self._factories.get((config.provider_type, config.capability))
        if factory is None:
            raise ProviderConfigurationError("Unsupported provider type and capability.")
        return factory(config, secret)

    @staticmethod
    def _policy(config: ProviderConfig) -> ProviderRequestPolicy:
        values = config.config_json or {}
        return ProviderRequestPolicy(
            connect_timeout=float(values.get("connect_timeout", 10)),
            read_timeout=float(values.get("read_timeout", 45)),
            max_attempts=max(1, min(int(values.get("max_attempts", 3)), 5)),
            backoff_seconds=max(0, float(values.get("backoff_seconds", 0.25))),
        )

    @classmethod
    def _openai_embedding(cls, config: ProviderConfig, secret: str | None) -> EmbeddingProvider:
        return OpenAICompatibleEmbeddingProvider(
            base_url=config.base_url or "https://api.openai.com/v1",
            model=config.model,
            dimension=config.dimension or 0,
            secret=secret,
            policy=cls._policy(config),
        )

    @classmethod
    def _openai_chat(cls, config: ProviderConfig, secret: str | None) -> ChatProvider:
        return OpenAICompatibleChatProvider(
            base_url=config.base_url or "https://api.openai.com/v1",
            model=config.model,
            secret=secret,
            policy=cls._policy(config),
        )

    @classmethod
    def _gemini_embedding(cls, config: ProviderConfig, secret: str | None) -> EmbeddingProvider:
        return GoogleGeminiEmbeddingProvider(
            base_url=config.base_url or "https://generativelanguage.googleapis.com/v1beta/openai",
            model=config.model,
            dimension=config.dimension or 0,
            secret=secret,
            policy=cls._policy(config),
        )

    @classmethod
    def _gemini_chat(cls, config: ProviderConfig, secret: str | None) -> ChatProvider:
        return GoogleGeminiChatProvider(
            base_url=config.base_url or "https://generativelanguage.googleapis.com/v1beta/openai",
            model=config.model,
            secret=secret,
            policy=cls._policy(config),
        )

    @staticmethod
    def _local_embedding(config: ProviderConfig, secret: str | None) -> EmbeddingProvider:
        values = config.config_json or {}
        return LocalSentenceTransformerProvider(
            model=config.model,
            dimension=config.dimension or 0,
            batch_size=int(values.get("batch_size", 32)),
            max_concurrency=int(values.get("max_concurrency", 2)),
        )

    @classmethod
    def _ollama_chat(cls, config: ProviderConfig, secret: str | None) -> ChatProvider:
        return OllamaChatProvider(
            base_url=config.base_url or "http://ollama:11434",
            model=config.model,
            policy=cls._policy(config),
            config=config.config_json,
        )
