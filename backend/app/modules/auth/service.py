import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.modules.auth.email import EmailSender, send_password_reset_email
from app.modules.auth.models import IdentityProvider, PasswordResetToken, UserIdentity, UserSession
from app.modules.users.models import User


@dataclass(frozen=True)
class AuthResult:
    access_token: str
    refresh_token: str
    session_id: uuid.UUID


class AuthService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        email_sender: EmailSender,
        settings: Settings,
    ) -> None:
        self.session = session
        self.email_sender = email_sender
        self.settings = settings

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    async def login(self, email: str, password: str) -> AuthResult:
        email = self.normalize_email(email)
        user = await self.session.scalar(select(User).where(func.lower(User.email) == email))
        identity = (
            await self.session.scalar(
                select(UserIdentity).where(
                    UserIdentity.user_id == user.id, UserIdentity.provider == IdentityProvider.LOCAL
                )
            )
            if user
            else None
        )
        if (
            identity is None
            or not identity.password_hash
            or not verify_password(password, identity.password_hash)
        ):
            raise AppError(
                "INVALID_CREDENTIALS", "Email or password is incorrect.", status_code=401
            )
        if user.status == "PENDING_VERIFICATION":
            raise AppError(
                "EMAIL_VERIFICATION_REQUIRED", "Email verification is required.", status_code=403
            )
        if user.status != "ACTIVE":
            raise AppError(
                "ACCOUNT_UNAVAILABLE", "The user account is unavailable.", status_code=403
            )
        now = datetime.now(UTC)
        user.last_login_at = now
        identity.last_used_at = now
        result = await self._create_session(user)
        await self.session.commit()
        return result

    async def forgot_password(self, email: str) -> None:
        email = self.normalize_email(email)
        user = await self.session.scalar(select(User).where(func.lower(User.email) == email))
        if user is None or user.status not in {"ACTIVE", "PENDING_VERIFICATION"}:
            return
        now = datetime.now(UTC)
        await self.session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now)
        )
        raw_token = generate_opaque_token()
        self.session.add(
            PasswordResetToken(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=now + timedelta(minutes=self.settings.password_reset_ttl_minutes),
            )
        )
        await self.session.commit()
        reset_url = (
            f"{self.settings.frontend_url.rstrip('/')}/auth/reset-password?token={raw_token}"
        )
        await send_password_reset_email(self.email_sender, email, reset_url)

    async def reset_password(self, token: str, new_password: str) -> None:
        now = datetime.now(UTC)
        reset = await self.session.scalar(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == hash_token(token))
            .with_for_update()
        )
        if reset is None or reset.used_at is not None or reset.expires_at <= now:
            raise AppError(
                "INVALID_RESET_TOKEN", "Reset token is invalid or expired.", status_code=400
            )
        user = await self.session.get(User, reset.user_id)
        identity = await self.session.scalar(
            select(UserIdentity).where(
                UserIdentity.user_id == reset.user_id,
                UserIdentity.provider == IdentityProvider.LOCAL,
            )
        )
        if identity is None:
            identity = UserIdentity(
                id=uuid.uuid4(),
                user_id=reset.user_id,
                provider=IdentityProvider.LOCAL,
                provider_subject=user.email,
            )
            self.session.add(identity)
        identity.password_hash = hash_password(new_password)
        reset.used_at = now
        user.auth_version += 1
        user.status = "ACTIVE"
        user.email_verified_at = user.email_verified_at or now
        await self._revoke_user_sessions(user.id, now)
        await self.session.commit()

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> AuthResult:
        identity = await self.session.scalar(
            select(UserIdentity).where(
                UserIdentity.user_id == user.id, UserIdentity.provider == IdentityProvider.LOCAL
            )
        )
        if (
            identity is None
            or not identity.password_hash
            or not verify_password(current_password, identity.password_hash)
        ):
            raise AppError(
                "INVALID_CURRENT_PASSWORD", "Current password is incorrect.", status_code=400
            )
        now = datetime.now(UTC)
        identity.password_hash = hash_password(new_password)
        user.auth_version += 1
        await self._revoke_user_sessions(user.id, now)
        result = await self._create_session(user)
        await self.session.commit()
        return result

    async def refresh(self, refresh_token: str) -> AuthResult:
        now = datetime.now(UTC)
        current = await self.session.scalar(
            select(UserSession).where(UserSession.refresh_token_hash == hash_token(refresh_token))
        )
        if current is None:
            raise AppError(
                "INVALID_REFRESH_TOKEN", "Refresh token is invalid or expired.", status_code=401
            )
        if current.revoked_at is not None:
            await self._revoke_user_sessions(current.user_id, now)
            await self.session.commit()
            raise AppError(
                "REFRESH_TOKEN_REUSED", "Refresh token reuse was detected.", status_code=401
            )
        if current.expires_at <= now:
            current.revoked_at = now
            await self.session.commit()
            raise AppError(
                "INVALID_REFRESH_TOKEN", "Refresh token is invalid or expired.", status_code=401
            )
        user = await self.session.get(User, current.user_id)
        if user is None or user.status != "ACTIVE":
            raise AppError(
                "AUTHENTICATION_REQUIRED", "The user account is unavailable.", status_code=401
            )
        current.revoked_at = now
        result = await self._create_session(user)
        current.replaced_by_id = result.session_id
        await self.session.commit()
        return result

    async def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        current = await self.session.scalar(
            select(UserSession).where(UserSession.refresh_token_hash == hash_token(refresh_token))
        )
        if current and current.revoked_at is None:
            current.revoked_at = datetime.now(UTC)
            await self.session.commit()

    async def _create_session(self, user: User) -> AuthResult:
        raw_refresh = generate_opaque_token()
        session_id = uuid.uuid4()
        self.session.add(
            UserSession(
                id=session_id,
                user_id=user.id,
                refresh_token_hash=hash_token(raw_refresh),
                expires_at=datetime.now(UTC) + timedelta(days=self.settings.refresh_token_ttl_days),
            )
        )
        await self.session.flush()
        return AuthResult(
            access_token=create_access_token(
                user.id, self.settings, auth_version=user.auth_version, session_id=session_id
            ),
            refresh_token=raw_refresh,
            session_id=session_id,
        )

    async def _revoke_user_sessions(self, user_id: uuid.UUID, now: datetime) -> None:
        await self.session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
