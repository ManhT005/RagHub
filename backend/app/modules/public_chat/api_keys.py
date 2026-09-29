import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.modules.chatbots.models import ChatbotApiKey


def hash_api_key(raw_key: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), raw_key.encode(), hashlib.sha256).hexdigest()


def generate_api_key(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    environment = settings.app_env.lower()
    prefix = (
        "rhpk_test_"
        if environment in {"development", "dev", "local", "test"}
        else "rhpk_live_"
    )
    return prefix + secrets.token_urlsafe(32)


def _is_expired(expires_at: datetime | None, now: datetime) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


class ApiKeyService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def create(
        self, organization_id: UUID, chatbot_id: UUID, name: str, expires_at: datetime | None
    ) -> tuple[ChatbotApiKey, str]:
        now = datetime.now(UTC)
        if expires_at is not None:
            comparable = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
            if comparable <= now:
                raise AppError(
                    "INVALID_API_KEY_EXPIRY",
                    "API key expiry must be in the future.",
                    status_code=422,
                )
        raw_key = generate_api_key(self.settings)
        row = ChatbotApiKey(
            organization_id=organization_id,
            chatbot_id=chatbot_id,
            name=name,
            key_prefix=raw_key[:24],
            key_hash=hash_api_key(raw_key, self.settings.public_api_key_pepper),
            expires_at=expires_at,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row, raw_key

    async def verify(self, chatbot_id: UUID, organization_id: UUID, raw_key: str) -> ChatbotApiKey:
        digest = hash_api_key(raw_key, self.settings.public_api_key_pepper)
        row = await self.session.scalar(
            select(ChatbotApiKey).where(
                ChatbotApiKey.chatbot_id == chatbot_id,
                ChatbotApiKey.organization_id == organization_id,
                ChatbotApiKey.key_hash == digest,
            )
        )
        if row is None:
            raise AppError("INVALID_API_KEY", "The public API key is invalid.", status_code=403)
        if row.revoked_at is not None:
            raise AppError(
                "API_KEY_REVOKED", "The public API key has been revoked.", status_code=403
            )
        now = datetime.now(UTC)
        if _is_expired(row.expires_at, now):
            raise AppError("API_KEY_EXPIRED", "The public API key has expired.", status_code=403)
        row.last_used_at = now
        await self.session.commit()
        return row

    async def list(self, organization_id: UUID, chatbot_id: UUID) -> list[ChatbotApiKey]:
        return list(
            await self.session.scalars(
                select(ChatbotApiKey)
                .where(
                    ChatbotApiKey.organization_id == organization_id,
                    ChatbotApiKey.chatbot_id == chatbot_id,
                )
                .order_by(ChatbotApiKey.created_at.desc())
            )
        )

    async def revoke(self, organization_id: UUID, chatbot_id: UUID, key_id: UUID) -> ChatbotApiKey:
        row = await self.session.scalar(
            select(ChatbotApiKey).where(
                ChatbotApiKey.id == key_id,
                ChatbotApiKey.organization_id == organization_id,
                ChatbotApiKey.chatbot_id == chatbot_id,
            )
        )
        if row is None:
            raise AppError("API_KEY_NOT_FOUND", "API key was not found.", status_code=404)
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            await self.session.commit()
            await self.session.refresh(row)
        return row
