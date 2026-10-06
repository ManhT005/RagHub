from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import Response
from fastapi.security import HTTPAuthorizationCredentials

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import decode_token, hash_password, hash_token
from app.modules.auth.cookies import delete_refresh_cookie, set_refresh_cookie
from app.modules.auth.models import PasswordResetToken, UserIdentity, UserSession
from app.modules.auth.service import AuthService
from app.modules.users.models import User


def service(session):
    return AuthService(session=session, email_sender=AsyncMock(), settings=Settings(_env_file=None))


async def create_user(sessions):
    async with sessions() as session:
        user = User(email="owner@example.com", status="ACTIVE", email_verified_at=datetime.now(UTC))
        session.add(user)
        await session.flush()
        session.add(
            UserIdentity(
                user_id=user.id,
                provider="LOCAL",
                provider_subject=user.email,
                password_hash=hash_password("original-password"),
            )
        )
        await session.commit()
        return user.id


@pytest.mark.integration
async def test_login_rotation_reuse_and_persistence(isolated_sessions):
    sessions = isolated_sessions
    await create_user(sessions)
    async with sessions() as session:
        initial = await service(session).login("OWNER@example.com", "original-password")
        persisted = await session.get(UserSession, initial.session_id)
        assert persisted.refresh_token_hash == hash_token(initial.refresh_token)
        assert initial.refresh_token not in persisted.refresh_token_hash
    # A new connection/service models process restart: no in-memory session state.
    async with sessions() as session:
        rotated = await service(session).refresh(initial.refresh_token)
        previous = await session.get(UserSession, initial.session_id)
        assert previous.revoked_at and previous.replaced_by_id == rotated.session_id
        assert (
            decode_token(rotated.access_token, Settings(_env_file=None)).session_id
            == rotated.session_id
        )
    async with sessions() as session:
        other_device = await service(session).login("owner@example.com", "original-password")
        with pytest.raises(AppError) as error:
            await service(session).refresh(initial.refresh_token)
        assert error.value.code == "REFRESH_TOKEN_REUSED"
        assert (await session.get(UserSession, rotated.session_id)).revoked_at is None
        previous = await session.get(UserSession, initial.session_id)
        previous.revoked_at = datetime.now(UTC) - timedelta(seconds=11)
        await session.commit()
        with pytest.raises(AppError):
            await service(session).refresh(initial.refresh_token)
        assert (await session.get(UserSession, rotated.session_id)).revoked_at
        assert (await session.get(UserSession, other_device.session_id)).revoked_at is None


@pytest.mark.integration
@pytest.mark.parametrize("state", ["expired", "revoked", "disabled", "auth_version"])
async def test_rejects_invalid_sessions(isolated_sessions, state):
    user_id = await create_user(isolated_sessions)
    async with isolated_sessions() as session:
        initial = await service(session).login("owner@example.com", "original-password")
        current = await session.get(UserSession, initial.session_id)
        if state == "expired":
            current.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif state == "revoked":
            current.revoked_at = datetime.now(UTC)
        elif state == "disabled":
            (await session.get(User, user_id)).status = "DISABLED"
        else:
            (await session.get(User, user_id)).auth_version += 1
        await session.commit()
        with pytest.raises(AppError):
            await service(session).refresh(initial.refresh_token)


@pytest.mark.integration
async def test_logout_revokes_refresh(isolated_sessions):
    await create_user(isolated_sessions)
    async with isolated_sessions() as session:
        auth = service(session)
        initial = await auth.login("owner@example.com", "original-password")
        await auth.logout(initial.refresh_token)
        await auth.logout(None)
        assert (await session.get(UserSession, initial.session_id)).revoked_at
        with pytest.raises(AppError):
            await auth.refresh(initial.refresh_token)


@pytest.mark.integration
async def test_logout_invalidates_access_token_immediately(isolated_sessions, monkeypatch):
    from app.core.auth import get_current_user

    await create_user(isolated_sessions)
    async with isolated_sessions() as session:
        auth = service(session)
        issued = await auth.login("owner@example.com", "original-password")
        monkeypatch.setattr("app.core.auth.get_settings", lambda: auth.settings)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=issued.access_token)
        assert await get_current_user(credentials, session)
        await auth.logout(issued.refresh_token)
        with pytest.raises(AppError) as error:
            await get_current_user(credentials, session)
        assert error.value.code == "AUTHENTICATION_REQUIRED"


@pytest.mark.integration
@pytest.mark.parametrize("operation", ["change", "reset"])
async def test_password_operations_revoke_old_refresh_and_auth_version(
    isolated_sessions, operation
):
    user_id = await create_user(isolated_sessions)
    async with isolated_sessions() as session:
        auth = service(session)
        old = await auth.login("owner@example.com", "original-password")
        user = await session.get(User, user_id)
        if operation == "change":
            new = await auth.change_password(user, "original-password", "updated-password")
            assert decode_token(new.access_token, auth.settings).auth_version == 1
        else:
            session.add(
                PasswordResetToken(
                    user_id=user_id,
                    token_hash=hash_token("reset-token"),
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                )
            )
            await session.commit()
            await auth.reset_password("reset-token", "updated-password")
        assert user.auth_version == 1
        assert (await session.get(UserSession, old.session_id)).revoked_at
        with pytest.raises(AppError):
            await auth.refresh(old.refresh_token)


def test_cookie_set_and_delete_have_matching_security_scope():
    from uuid import uuid4

    from app.modules.auth.service import AuthResult

    settings = Settings(_env_file=None)
    response = Response()
    set_refresh_cookie(response, AuthResult("access", "refresh", uuid4()), settings)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Path=/api/v1/auth" in cookie
    assert "SameSite=lax" in cookie and "Max-Age=604800" in cookie
    response = Response()
    delete_refresh_cookie(response, settings)
    assert "Path=/api/v1/auth" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
