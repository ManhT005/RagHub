from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status

from app.core.auth import get_current_user
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.modules.auth.dependencies import get_auth_service
from app.modules.auth.schemas import (
    Credentials,
    CurrentUserResponse,
    EmailRequest,
    MessageResponse,
    PasswordChangeRequest,
    PasswordResetRequest,
    TokenResponse,
)
from app.modules.auth.service import AuthResult, AuthService
from app.modules.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(
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


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: Credentials,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    return _set_refresh_cookie(
        response, await service.login(payload.email, payload.password), settings
    )


@router.post(
    "/password/forgot", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED
)
async def forgot_password(
    payload: EmailRequest, service: Annotated[AuthService, Depends(get_auth_service)]
) -> MessageResponse:
    await service.forgot_password(payload.email)
    return MessageResponse(message="If the account exists, a reset link has been sent.")


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: PasswordResetRequest, service: Annotated[AuthService, Depends(get_auth_service)]
) -> Response:
    await service.reset_password(payload.token, payload.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password/change", response_model=TokenResponse)
async def change_password(
    payload: PasswordChangeRequest,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    result = await service.change_password(user, payload.current_password, payload.new_password)
    return _set_refresh_cookie(response, result, settings)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    if not refresh_token:
        raise AppError(
            "REFRESH_TOKEN_REQUIRED", "A refresh token cookie is required.", status_code=401
        )
    return _set_refresh_cookie(response, await service.refresh(refresh_token), settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> Response:
    await service.logout(refresh_token)
    response.delete_cookie("refresh_token", path=f"{settings.api_v1_prefix}/auth")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=CurrentUserResponse)
async def current_user(user: Annotated[User, Depends(get_current_user)]) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=str(user.id), email=user.email, email_verified=user.email_verified_at is not None
    )
