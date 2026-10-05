from raghub_core.domain.providers.descriptor import ProviderDescriptor

from app.modules.ai_providers.models import EmbeddingIndexVersion, ProviderConfig


def provider_descriptor(
    config: ProviderConfig, version: EmbeddingIndexVersion | None = None
) -> ProviderDescriptor:
    source = version or config
    return ProviderDescriptor(
        provider_type=source.provider_type,
        capability=config.capability,
        model=source.model,
        base_url=source.base_url,
        dimension=source.dimension,
        options=source.config_json or {},
    )
