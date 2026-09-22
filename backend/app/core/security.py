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


def create_access_token(user_id: UUID, settings: Settings, token_type: str = "access") -> str:
    now = datetime.now(UTC)
    expiry = (
        timedelta(minutes=settings.access_token_ttl_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_ttl_days)
    )
    return jwt.encode(
        {"sub": str(user_id), "type": token_type, "iat": now, "exp": now + expiry},
        settings.app_secret_key,
        algorithm="HS256",
    )


def decode_token(token: str, settings: Settings, expected_type: str = "access") -> UUID:
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
        if payload.get("type") != expected_type:
            raise jwt.InvalidTokenError(f"Expected a {expected_type} token")
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise ValueError("Invalid access token") from exc
