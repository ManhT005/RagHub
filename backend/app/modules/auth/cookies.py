from fastapi import Response

from app.core.config import Settings
from app.modules.auth.schemas import TokenResponse
from app.modules.auth.service import AuthResult


def set_refresh_cookie(
    response: Response, result: AuthResult, settings: Settings
) -> TokenResponse:
    response.set_cookie(
        "refresh_token",
        result.refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=f"{settings.api_v1_prefix}/auth",
        max_age=settings.refresh_token_ttl_days * 86400,
    )
    return TokenResponse(access_token=result.access_token)


def delete_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        "refresh_token",
        path=f"{settings.api_v1_prefix}/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
