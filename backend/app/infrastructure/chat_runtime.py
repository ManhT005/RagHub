from app.core_domain.chatbots.models import ChatbotConfig
from app.core_domain.retrieval.models import RetrievalScope, RetrievedChunk
from app.infrastructure.providers import ProviderResolverAdapter
from app.infrastructure.retrieval_mapping import chunk_from_hit


class ChatbotRuntimeReader:
    def __init__(self, loader) -> None:
        self.loader = loader

    async def get(self, organization_id, chatbot_id) -> ChatbotConfig:
        chatbot = await self.loader(organization_id, chatbot_id)
        return ChatbotConfig(
            chatbot.id,
            RetrievalScope(organization_id, chatbot.workspace_id),
            getattr(chatbot, "name", ""),
            getattr(chatbot, "system_prompt", ""),
            chatbot.retrieval_limit,
            chatbot.published,
            getattr(chatbot, "model", None),
        )


class RuntimeRetrievalAdapter:
    def __init__(self, search_factory) -> None:
        self.search_factory = search_factory

    async def retrieve(self, scope, query, limit) -> list[RetrievedChunk]:
        hits = await self.search_factory().retrieve(
            scope.organization_id,
            scope.workspace_id,
            query,
            limit,
        )
        return [chunk_from_hit(hit) for hit in hits]


class LazyProviderResolverAdapter:
    def __init__(self, resolver_factory) -> None:
        self.resolver_factory = resolver_factory

    async def resolve_chat(self, scope):
        return await ProviderResolverAdapter(self.resolver_factory()).resolve_chat(scope)

    async def resolve_embedding(self, scope):
        return await ProviderResolverAdapter(self.resolver_factory()).resolve_embedding(scope)

    async def resolve_embedding_version(self, version_id):
        return await ProviderResolverAdapter(self.resolver_factory()).resolve_embedding_version(
            version_id
        )
