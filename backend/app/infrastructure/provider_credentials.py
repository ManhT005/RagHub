from app.core.config import get_settings
from raghub_core.domain.providers.enums import ProviderType


def resolve_provider_secret(config, cipher, *, provider_type: str | None = None) -> str | None:
    """Keep server credential fallback outside the detached provider registry."""
    secret = cipher.decrypt(config.encrypted_secret) if config.encrypted_secret else None
    if (provider_type or config.provider_type) == ProviderType.GOOGLE_GEMINI:
        return secret or get_settings().gemini_api_key or None
    return secret
