from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.installation.service import InitializeInstallationService


def get_installation_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InitializeInstallationService:
    return InitializeInstallationService(session)
