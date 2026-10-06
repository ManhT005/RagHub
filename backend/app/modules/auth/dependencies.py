from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.redis import get_redis
from app.modules.auth.email import build_email_sender
from app.modules.auth.rate_limit import AuthRateLimiter
from app.modules.auth.service import AuthService


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(
        session=session,
        email_sender=build_email_sender(settings),
        settings=settings,
    )


def get_auth_rate_limiter(
    redis: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthRateLimiter:
    return AuthRateLimiter(redis, settings)
