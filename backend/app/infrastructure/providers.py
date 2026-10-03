from uuid import UUID

from app.core_domain.providers.errors import ProviderConfigurationError
from app.core_domain.retrieval.models import RetrievalScope
from app.modules.ai_providers.models import EmbeddingIndexVersion
from app.modules.ai_providers.resolver import ProviderResolver
from app.ports.provider_resolver import ChatRuntime, EmbeddingRuntime


class ProviderResolverAdapter:
    def __init__(self, resolver: ProviderResolver) -> None:
        self.resolver = resolver

    async def resolve_embedding(self, scope: RetrievalScope) -> EmbeddingRuntime:
        resolved = await self.resolver.embedding_for_workspace(
            scope.organization_id, scope.workspace_id
        )
        return EmbeddingRuntime(
            resolved.provider, resolved.index_version.index_name, resolved.index_version.dimension
        )

    async def resolve_embedding_version(self, version_id: UUID) -> EmbeddingRuntime:
        version = await self.resolver.session.get(EmbeddingIndexVersion, version_id)
        if version is None:
            raise ProviderConfigurationError("Embedding index version was not found.")
        resolved = await self.resolver.embedding_for_version(version)
        return EmbeddingRuntime(resolved.provider, version.index_name, version.dimension)

    async def resolve_chat(self, scope: RetrievalScope) -> ChatRuntime:
        resolved = await self.resolver.chat_for_workspace(scope.organization_id, scope.workspace_id)
        return ChatRuntime(resolved.provider, resolved.config.provider_type, resolved.config.model)
