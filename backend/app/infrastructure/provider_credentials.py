from app.core.config import get_settings
from raghub_core.domain.providers.enums import ProviderType


def resolve_provider_secret(config, cipher, *, provider_type: str | None = None) -> str | None:
    """Keep server credential fallback outside the detached provider registry."""
    connection = getattr(config, "connection", None)
    encrypted = connection.encrypted_secret if connection is not None else config.encrypted_secret
    secret = cipher.decrypt(encrypted) if encrypted else None
    if (provider_type or config.provider_type) == ProviderType.GOOGLE_GEMINI:
        return secret or get_settings().gemini_api_key or None
    return secret
