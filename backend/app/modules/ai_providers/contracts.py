from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ChatOptions:
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stop: list[str] | None = None


@dataclass(frozen=True)
class EmbeddingMetadata:
    provider_name: str
    model: str
    dimension: int


@dataclass(frozen=True)
class ProviderTestResult:
    status: str
    capability: str
    provider: str
    model: str
    latency_ms: int
    dimension: int | None = None
    details: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class EmbeddingProvider(Protocol):
    metadata: EmbeddingMetadata

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


@runtime_checkable
class ChatProvider(Protocol):
    provider_name: str
    model: str

    def stream_chat(
        self, messages: list[ChatMessage], options: ChatOptions
    ) -> AsyncIterator[str]: ...
