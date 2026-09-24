from collections.abc import AsyncIterator

from app.modules.ai_providers.contracts import (
    ChatMessage,
    ChatOptions,
    ChatProvider,
    EmbeddingMetadata,
    EmbeddingProvider,
)


class EmbeddingStub:
    metadata = EmbeddingMetadata("stub", "model", 2)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


class ChatStub:
    provider_name = "stub"
    model = "model"

    async def stream_chat(
        self, messages: list[ChatMessage], options: ChatOptions
    ) -> AsyncIterator[str]:
        yield "OK"


def test_runtime_provider_contracts() -> None:
    assert isinstance(EmbeddingStub(), EmbeddingProvider)
    assert isinstance(ChatStub(), ChatProvider)
