from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_providers.models import ProviderConfig


class ProviderConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_organization(self, organization_id: UUID) -> list[ProviderConfig]:
        return list(
            await self.session.scalars(
                select(ProviderConfig)
                .where(ProviderConfig.organization_id == organization_id)
                .order_by(ProviderConfig.name)
            )
        )

    async def get_scoped(self, organization_id: UUID, provider_id: UUID) -> ProviderConfig | None:
        return await self.session.scalar(
            select(ProviderConfig).where(
                ProviderConfig.id == provider_id,
                ProviderConfig.organization_id == organization_id,
            )
        )
