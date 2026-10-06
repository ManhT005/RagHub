from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status

from app.core.auth import get_current_user
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.delivery.public.admission import client_ip
from app.modules.auth.cookies import delete_refresh_cookie, set_refresh_cookie
from app.modules.auth.dependencies import get_auth_rate_limiter, get_auth_service
from app.modules.auth.rate_limit import AuthRateLimiter
from app.modules.auth.schemas import (
    Credentials,
    CurrentUserResponse,
    EmailRequest,
    MessageResponse,
    PasswordChangeRequest,
    PasswordResetRequest,
    TokenResponse,
)
from app.modules.auth.service import AuthService
from app.modules.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: Credentials,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    limits: Annotated[AuthRateLimiter, Depends(get_auth_rate_limiter)],
) -> TokenResponse:
    await limits.login(client_ip(request, settings), payload.email)
    return set_refresh_cookie(
        response, await service.login(payload.email, payload.password), settings
    )


@router.post(
    "/password/forgot", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED
)
async def forgot_password(
    payload: EmailRequest,
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    limits: Annotated[AuthRateLimiter, Depends(get_auth_rate_limiter)],
) -> MessageResponse:
    await limits.password(client_ip(request, settings), payload.email)
    await service.forgot_password(payload.email)
    return MessageResponse(message="If the account exists, a reset link has been sent.")


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: PasswordResetRequest,
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    limits: Annotated[AuthRateLimiter, Depends(get_auth_rate_limiter)],
) -> Response:
    await limits.password(client_ip(request, settings), payload.token)
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
    return set_refresh_cookie(response, result, settings)


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
    return set_refresh_cookie(response, await service.refresh(refresh_token), settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> Response:
    await service.logout(refresh_token)
    delete_refresh_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=CurrentUserResponse)
async def current_user(user: Annotated[User, Depends(get_current_user)]) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=str(user.id), email=user.email, email_verified=user.email_verified_at is not None
    )
