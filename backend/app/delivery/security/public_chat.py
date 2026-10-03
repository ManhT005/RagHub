from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.delivery.security.origins import origin_is_allowed
from app.modules.chatbots.embed import hash_embed_key
from app.modules.chatbots.models import Chatbot
from app.modules.workspaces.models import Workspace


class PublicChatResolver:
    """Resolve tenant scope from a published embed key, never from request tenant IDs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(self, raw_key: str, origin: str | None) -> Chatbot:
        chatbot = await self.session.scalar(
            select(Chatbot)
            .join(Workspace, Workspace.id == Chatbot.workspace_id)
            .where(
                Chatbot.embed_key_hash == hash_embed_key(raw_key),
                Chatbot.published.is_(True),
                Workspace.organization_id == Chatbot.organization_id,
                Workspace.deleted_at.is_(None),
            )
        )
        if chatbot is None:
            raise AppError(
                "EMBED_CHATBOT_NOT_FOUND", "This chatbot is unavailable.", status_code=404
            )
        if not origin_is_allowed(origin, chatbot.allowed_origins):
            raise AppError(
                "EMBED_ORIGIN_NOT_ALLOWED", "This website is not allowed.", status_code=403
            )
        return chatbot
