from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.modules.chatbots.models import Chatbot, ChatbotAllowedOrigin
from app.modules.public_chat.api_keys import ApiKeyService
from app.modules.public_chat.origin import normalize_origin


@dataclass(frozen=True)
class PublicAccessContext:
    chatbot: Chatbot
    access_mode: str
    origin: str | None

    @property
    def chatbot_id(self) -> UUID:
        return self.chatbot.id

    @property
    def organization_id(self) -> UUID:
        return self.chatbot.organization_id


class PublicChatAccessService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(self, public_key: str) -> Chatbot:
        chatbot = await self.session.scalar(
            select(Chatbot).where(Chatbot.public_key == public_key, Chatbot.published.is_(True))
        )
        if chatbot is None:
            raise AppError(
                "PUBLIC_CHATBOT_NOT_FOUND", "Public chatbot was not found.", status_code=404
            )
        return chatbot

    async def authorize(
        self, chatbot: Chatbot, origin_header: str | None, raw_api_key: str | None
    ) -> PublicAccessContext:
        if origin_header is not None:
            try:
                origin = normalize_origin(origin_header)
            except ValueError as exc:
                raise AppError(
                    "ORIGIN_NOT_ALLOWED",
                    "This origin is not allowed to use the chatbot.",
                    status_code=403,
                ) from exc
            allowed = await self.session.scalar(
                select(ChatbotAllowedOrigin.id).where(
                    ChatbotAllowedOrigin.chatbot_id == chatbot.id,
                    ChatbotAllowedOrigin.origin == origin,
                )
            )
            if allowed is None:
                raise AppError(
                    "ORIGIN_NOT_ALLOWED",
                    "This origin is not allowed to use the chatbot.",
                    status_code=403,
                )
            return PublicAccessContext(chatbot, "origin", origin)
        if not raw_api_key:
            raise AppError(
                "PUBLIC_ACCESS_DENIED",
                "An allowed origin or public API key is required.",
                status_code=403,
            )
        await ApiKeyService(self.session).verify(
            chatbot.id, chatbot.organization_id, raw_api_key
        )
        return PublicAccessContext(chatbot, "api_key", None)


def cors_headers(context: PublicAccessContext) -> dict[str, str]:
    if context.origin is None:
        return {}
    return {
        "Access-Control-Allow-Origin": context.origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-RagHub-API-Key",
        "Vary": "Origin",
    }
