"""Explicit, idempotent import of environment credentials into an organization's connections."""

from sqlalchemy import select

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.modules.ai_providers.catalog import CATALOG
from app.modules.ai_providers.control_schemas import ConnectionInput
from app.modules.ai_providers.crypto import ProviderSecretCipher
from app.modules.ai_providers.models import ProviderConnection
from app.modules.organizations.models import Organization

BOOTSTRAP_KEYS = {
    "gemini": "gemini_api_key",
    "openai": "openai_api_key",
    "groq": "groq_api_key",
    "cerebras": "cerebras_api_key",
    "openrouter": "openrouter_api_key",
    "voyage": "voyage_api_key",
    "siliconflow": "siliconflow_api_key",
    "cloudflare-workers-ai": "cloudflare_api_token",
    "huggingface": "huggingface_token",
    "nvidia-nim": "nvidia_nim_api_key",
}


class ProviderBootstrapService:
    def __init__(self, session, settings=None):
        self.session = session
        self.settings = settings or get_settings()
        self.cipher = ProviderSecretCipher(self.settings.provider_master_key)

    async def import_env(self, organization_id, *, fill_legacy_gemini=False):
        organization = await self.session.scalar(
            select(Organization).where(Organization.id == organization_id).with_for_update()
        )
        if organization is None:
            raise AppError("ORGANIZATION_NOT_FOUND", "Organization not found.", status_code=404)
        imported = []
        for item in CATALOG:
            key = BOOTSTRAP_KEYS.get(item.id)
            secret = getattr(self.settings, key, "") if key else ""
            if not secret or item.status not in {"SUPPORTED", "BETA"}:
                continue
            existing = await self.session.scalar(
                select(ProviderConnection)
                .where(
                    ProviderConnection.organization_id == organization_id,
                    ProviderConnection.catalog_id == item.id,
                )
                .order_by(ProviderConnection.created_at)
                .limit(1)
            )
            if existing:
                if fill_legacy_gemini and item.id == "gemini" and not existing.encrypted_secret:
                    existing.encrypted_secret = self.cipher.encrypt(secret)
                    existing.status = "UNTESTED"
                    imported.append(existing)
                continue
            options = {"credential_source": "BOOTSTRAP"}
            if item.id == "cloudflare-workers-ai":
                if not self.settings.cloudflare_account_id:
                    continue
                options["account_id"] = self.settings.cloudflare_account_id
            payload = ConnectionInput(
                name=item.name + " (bootstrap)",
                catalog_id=item.id,
                provider_type=item.provider_type,
                secret=secret,
                config_json=options,
            )
            connection = ProviderConnection(
                organization_id=organization_id,
                name=payload.name,
                catalog_id=item.id,
                provider_type=item.provider_type,
                base_url=payload.base_url,
                config_json=payload.config_json,
                enabled=True,
                encrypted_secret=self.cipher.encrypt(secret),
                status="UNTESTED",
            )
            self.session.add(connection)
            imported.append(connection)
        await self.session.flush()
        return imported
