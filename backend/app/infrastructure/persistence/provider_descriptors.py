from raghub_core.domain.providers.descriptor import ProviderDescriptor
from raghub_core.domain.providers.errors import ProviderConfigurationError

from app.modules.ai_providers.models import EmbeddingIndexVersion, ProviderConfig


def provider_descriptor(
    config: ProviderConfig, version: EmbeddingIndexVersion | None = None
) -> ProviderDescriptor:
    source = version or config
    connection = config.connection
    if connection and config.provider_type in {
        "OPENAI_COMPATIBLE",
        "GOOGLE_GEMINI",
        "VOYAGE",
        "CLOUDFLARE_WORKERS_AI",
        "HUGGINGFACE_INFERENCE",
    }:
        from app.modules.ai_providers.catalog import connection_catalog_id, supported_catalog_by_id
        from app.modules.ai_providers.schemas import validate_connection_endpoint

        try:
            validate_connection_endpoint(connection)
            catalog = supported_catalog_by_id(connection_catalog_id(connection))
            if (
                catalog.locked_base_url
                and (source.base_url or "").rstrip("/") != connection.base_url
            ):
                raise ValueError("Snapshot endpoint mismatch")
        except ValueError as exc:
            raise ProviderConfigurationError(
                "Provider endpoint does not match its identity."
            ) from exc
    return ProviderDescriptor(
        provider_type=source.provider_type,
        capability=config.capability,
        model=source.model,
        base_url=source.base_url,
        dimension=source.dimension,
        options=source.config_json or {},
    )
