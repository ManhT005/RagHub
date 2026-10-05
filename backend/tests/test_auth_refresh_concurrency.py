import asyncio

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.modules.auth.models import UserSession
from tests.test_auth_refresh import create_user, service


@pytest.mark.integration
async def test_concurrent_refresh_creates_only_one_rotation(isolated_sessions):
    await create_user(isolated_sessions)
    async with isolated_sessions() as session:
        initial = await service(session).login("owner@example.com", "original-password")

    async def refresh():
        async with isolated_sessions() as session:
            return await service(session).refresh(initial.refresh_token)

    results = await asyncio.gather(refresh(), refresh(), return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, AppError) for result in results) == 1
    async with isolated_sessions() as session:
        assert await session.scalar(select(func.count()).select_from(UserSession)) == 2
        # Reuse detection may revoke the winner as well, but can never create two children.
        assert (
            await session.scalar(
                select(func.count())
                .select_from(UserSession)
                .where(UserSession.revoked_at.is_(None))
            )
            <= 1
        )
