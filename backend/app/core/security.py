import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import Settings

_passwords = PasswordHasher()


def hash_password(password: str) -> str:
    return _passwords.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _passwords.verify(password_hash, password)
    except VerifyMismatchError:
        return False


@dataclass(frozen=True)
class TokenClaims:
    user_id: UUID
    token_type: str
    auth_version: int
    session_id: UUID | None


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_otp(email: str, otp: str, secret: str) -> str:
    message = f"{email.strip().lower()}:{otp}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_otp(email: str, otp: str, digest: str, secret: str) -> bool:
    return hmac.compare_digest(hash_otp(email, otp, secret), digest)


def create_access_token(
    user_id: UUID,
    settings: Settings,
    token_type: str = "access",
    *,
    auth_version: int = 0,
    session_id: UUID | None = None,
) -> str:
    now = datetime.now(UTC)
    expiry = (
        timedelta(minutes=settings.access_token_ttl_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_ttl_days)
    )
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": token_type,
            "av": auth_version,
            "sid": str(session_id) if session_id else None,
            "iat": now,
            "exp": now + expiry,
        },
        settings.app_secret_key,
        algorithm="HS256",
    )


def decode_token(
    token: str, settings: Settings, expected_type: str = "access"
) -> TokenClaims:
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
        if payload.get("type") != expected_type:
            raise jwt.InvalidTokenError(f"Expected a {expected_type} token")
        session_id = payload.get("sid")
        return TokenClaims(
            user_id=UUID(payload["sub"]),
            token_type=payload["type"],
            auth_version=int(payload.get("av", 0)),
            session_id=UUID(session_id) if session_id else None,
        )
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise ValueError("Invalid access token") from exc
