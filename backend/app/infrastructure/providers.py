from uuid import UUID

from raghub_core.domain.providers.errors import ProviderConfigurationError
from raghub_core.domain.retrieval.models import RetrievalScope
from raghub_core.ports.provider_resolver import ChatRuntime, EmbeddingRuntime

from app.modules.ai_providers.models import EmbeddingIndexVersion
from app.modules.ai_providers.resolver import ProviderResolver


class ProviderResolverAdapter:
    def __init__(self, resolver: ProviderResolver) -> None:
        self.resolver = resolver

    async def resolve_embedding(self, scope: RetrievalScope) -> EmbeddingRuntime:
        resolved = await self.resolver.embedding_for_workspace(
            scope.organization_id, scope.workspace_id
        )
        return EmbeddingRuntime(
            resolved.provider,
            resolved.index_version.index_name,
            resolved.index_version.dimension,
            quota_scope=await self._pool_scope(resolved.index_version),
            fingerprint=getattr(resolved.index_version, "embedding_fingerprint_v2", None)
            or getattr(resolved.index_version, "embedding_fingerprint", ""),
        )

    async def _pool_scope(self, version: EmbeddingIndexVersion) -> str | None:
        from raghub_core.domain.providers.enums import ProviderType
        from raghub_core.domain.providers.fingerprint import quota_scope
        provider_type = getattr(version, "provider_type", "")
        if provider_type != ProviderType.GOOGLE_GEMINI:
            return None
        if not getattr(version, "embedding_fingerprint_v2", None):
            return quota_scope(provider_type=provider_type, model=version.model)
        pool, _ = await self.resolver.embedding_pool_for_version(version)
        return pool.quota_scope

    async def resolve_embedding_version(self, version_id: UUID) -> EmbeddingRuntime:
        version = await self.resolver.session.get(EmbeddingIndexVersion, version_id)
        if version is None:
            raise ProviderConfigurationError("Embedding index version was not found.")
        resolved = await self.resolver.embedding_for_version(version)
        return EmbeddingRuntime(
            resolved.provider,
            version.index_name,
            version.dimension,
            quota_scope=await self._pool_scope(version),
            fingerprint=version.embedding_fingerprint_v2 or version.embedding_fingerprint,
        )

    async def resolve_chat(self, scope: RetrievalScope) -> ChatRuntime:
        resolved = await self.resolver.chat_for_workspace(scope.organization_id, scope.workspace_id)
        return ChatRuntime(resolved.provider, resolved.config.provider_type, resolved.config.model)
