from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.core_domain.providers.contracts import ChatProvider, EmbeddingProvider
from app.core_domain.retrieval.models import RetrievalScope


@dataclass(frozen=True)
class EmbeddingRuntime:
    provider: EmbeddingProvider
    index_name: str
    dimension: int


@dataclass(frozen=True)
class ChatRuntime:
    provider: ChatProvider
    provider_type: str
    model: str


class ProviderResolverPort(Protocol):
    async def resolve_embedding(self, scope: RetrievalScope) -> EmbeddingRuntime: ...
    async def resolve_embedding_version(self, version_id: UUID) -> EmbeddingRuntime: ...
    async def resolve_chat(self, scope: RetrievalScope) -> ChatRuntime: ...
