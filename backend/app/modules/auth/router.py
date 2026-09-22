from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.database import get_session
from app.core.exceptions import AppError
from app.core.security import create_access_token, decode_token, hash_password, verify_password
from app.modules.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    id: str
    email: EmailStr


def _response(user: User, response: Response) -> TokenResponse:
    settings = get_settings()
    response.set_cookie(
        "refresh_token",
        create_access_token(user.id, settings, "refresh"),
        httponly=True,
        samesite="lax",
        max_age=settings.refresh_token_ttl_days * 86400,
    )
    return TokenResponse(access_token=create_access_token(user.id, settings))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: Credentials,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    email = payload.email.lower()
    if await session.scalar(select(User.id).where(User.email == email)):
        raise AppError("EMAIL_ALREADY_REGISTERED", "Email is already registered.", status_code=409)
    user = User(email=email, password_hash=hash_password(payload.password))
    session.add(user)
    await session.commit()
    return _response(user, response)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: Credentials,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Email or password is incorrect.", status_code=401)
    return _response(user, response)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> Response:
    response.delete_cookie("refresh_token")
    return response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    if refresh_token is None:
        raise AppError(
            "REFRESH_TOKEN_REQUIRED", "A refresh token cookie is required.", status_code=401
        )
    try:
        user_id = decode_token(refresh_token, get_settings(), expected_type="refresh")
    except ValueError as exc:
        raise AppError(
            "INVALID_REFRESH_TOKEN", "The refresh token is invalid or expired.", status_code=401
        ) from exc
    user = await session.get(User, user_id)
    if user is None or user.status != "ACTIVE":
        raise AppError(
            "AUTHENTICATION_REQUIRED", "The user account is unavailable.", status_code=401
        )
    return _response(user, response)


@router.get("/me", response_model=CurrentUserResponse)
async def current_user(user: Annotated[User, Depends(get_current_user)]) -> CurrentUserResponse:
    return CurrentUserResponse(id=str(user.id), email=user.email)
