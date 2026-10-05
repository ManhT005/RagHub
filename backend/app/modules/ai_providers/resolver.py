from dataclasses import dataclass
from uuid import UUID

from raghub_core.domain.providers.contracts import ChatProvider, EmbeddingProvider
from raghub_core.domain.providers.enums import IndexVersionStatus, ProviderCapability
from raghub_core.domain.providers.errors import (
    ProviderConfigurationError,
    ProviderDisabledError,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.persistence.provider_descriptors import provider_descriptor
from app.infrastructure.provider_credentials import resolve_provider_secret
from app.modules.ai_providers.crypto import ProviderSecretCipher
from app.modules.ai_providers.models import EmbeddingIndexVersion, ProviderConfig
from app.modules.ai_providers.registry import ProviderRegistry
from app.modules.workspaces.models import Workspace


@dataclass(frozen=True)
class ResolvedEmbeddingProvider:
    provider: EmbeddingProvider
    config: ProviderConfig
    index_version: EmbeddingIndexVersion


@dataclass(frozen=True)
class ResolvedChatProvider:
    provider: ChatProvider
    config: ProviderConfig


class ProviderResolver:
    def __init__(
        self,
        session: AsyncSession,
        registry: ProviderRegistry | None = None,
        cipher: ProviderSecretCipher | None = None,
    ) -> None:
        self.session = session
        self.registry = registry or ProviderRegistry()
        self.cipher = cipher or ProviderSecretCipher(get_settings().provider_master_key)

    def _secret(self, config: ProviderConfig, provider_type: str | None = None) -> str | None:
        return resolve_provider_secret(config, self.cipher, provider_type=provider_type)

    @staticmethod
    def _validate(config: ProviderConfig | None, capability: ProviderCapability) -> ProviderConfig:
        if config is None:
            raise ProviderConfigurationError()
        if not config.enabled:
            raise ProviderDisabledError()
        if config.connection is not None and not config.connection.enabled:
            raise ProviderDisabledError()
        if config.capability != capability:
            raise ProviderConfigurationError("Provider capability does not match the binding.")
        return config

    async def embedding_for_workspace(
        self, organization_id: UUID, workspace_id: UUID
    ) -> ResolvedEmbeddingProvider:
        row = (
            await self.session.execute(
                select(Workspace, EmbeddingIndexVersion, ProviderConfig)
                .join(
                    EmbeddingIndexVersion,
                    EmbeddingIndexVersion.id == Workspace.active_embedding_index_version_id,
                )
                .join(ProviderConfig, ProviderConfig.id == EmbeddingIndexVersion.provider_config_id)
                .where(
                    Workspace.id == workspace_id,
                    Workspace.organization_id == organization_id,
                    Workspace.deleted_at.is_(None),
                    EmbeddingIndexVersion.status == IndexVersionStatus.ACTIVE,
                    EmbeddingIndexVersion.organization_id == organization_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise ProviderConfigurationError("Workspace has no active embedding index.")
        _, version, config = row
        self._validate(config, ProviderCapability.EMBEDDING)
        provider = self.registry.create(
            provider_descriptor(config, version), self._secret(config, version.provider_type)
        )
        return ResolvedEmbeddingProvider(provider, config, version)  # type: ignore[arg-type]

    async def chat_for_workspace(
        self, organization_id: UUID, workspace_id: UUID
    ) -> ResolvedChatProvider:
        row = (
            await self.session.execute(
                select(ProviderConfig)
                .join(Workspace, Workspace.chat_provider_id == ProviderConfig.id)
                .where(
                    Workspace.id == workspace_id,
                    Workspace.organization_id == organization_id,
                    Workspace.deleted_at.is_(None),
                    ProviderConfig.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        config = self._validate(row, ProviderCapability.CHAT)
        provider = self.registry.create(provider_descriptor(config), self._secret(config))
        return ResolvedChatProvider(provider, config)  # type: ignore[arg-type]

    async def embedding_for_version(
        self, version: EmbeddingIndexVersion
    ) -> ResolvedEmbeddingProvider:
        config = await self.session.scalar(
            select(ProviderConfig).where(
                ProviderConfig.id == version.provider_config_id,
                ProviderConfig.organization_id == version.organization_id,
            )
        )
        config = self._validate(config, ProviderCapability.EMBEDDING)
        provider = self.registry.create(
            provider_descriptor(config, version), self._secret(config, version.provider_type)
        )
        return ResolvedEmbeddingProvider(provider, config, version)  # type: ignore[arg-type]
