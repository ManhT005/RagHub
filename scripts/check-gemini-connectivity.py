"""Read-only connectivity check; never print provider credentials."""
import asyncio

import app.models  # noqa: F401
from sqlalchemy import select

from app.core.database import SessionFactory
from app.core.exceptions import AppError
from app.modules.ai_providers.models import ProviderConfig
from app.modules.ai_providers.service import ProviderConfigService


async def main():
    async with SessionFactory() as session:
        providers = list(await session.scalars(select(ProviderConfig).where(
            ProviderConfig.provider_type == "GOOGLE_GEMINI",
            ProviderConfig.capability == "EMBEDDING",
            ProviderConfig.enabled.is_(True),
        )))
        for provider in providers:
            try:
                result = await ProviderConfigService(session).test(
                    provider.organization_id, provider.id,
                )
                print(provider.name, result)
            except AppError as error:
                print(provider.name, error.code, error.message)


asyncio.run(main())
