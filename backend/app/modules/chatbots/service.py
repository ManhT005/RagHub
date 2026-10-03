from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import aclosing
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.rag import rag_use_case
from app.core.exceptions import AppError
from app.core_domain.rag.events import RagEvent
from app.core_domain.rag.models import StreamChatCommand
from app.core_domain.rag.prompt import EMPTY_CONTEXT_ANSWER as EMPTY_CONTEXT_ANSWER
from app.delivery.http.sse import event_payload
from app.infrastructure.persistence.conversations import ConversationRepositoryAdapter
from app.modules.ai_providers.resolver import ProviderResolver
from app.modules.chatbots.embed import (
    create_embed_key,
    hash_embed_key,
    origin_is_allowed,
    public_config,
)
from app.modules.chatbots.models import Chatbot
from app.modules.chatbots.schemas import ChatbotInput, ChatbotPatch, EmbedPublishInput
from app.modules.search.service import SearchService
from app.modules.workspaces.models import Workspace


class ChatbotService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _workspace(self, organization_id: UUID, workspace_id: UUID) -> Workspace:
        workspace = await self.session.scalar(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.organization_id == organization_id,
                Workspace.deleted_at.is_(None),
            )
        )
        if workspace is None:
            raise AppError(
                "WORKSPACE_NOT_FOUND",
                "Workspace was not found in the current organization.",
                status_code=404,
            )
        return workspace

    async def list(self, organization_id: UUID, workspace_id: UUID) -> list[Chatbot]:
        await self._workspace(organization_id, workspace_id)
        return list(
            await self.session.scalars(
                select(Chatbot)
                .where(
                    Chatbot.organization_id == organization_id, Chatbot.workspace_id == workspace_id
                )
                .order_by(Chatbot.name)
            )
        )

    async def create(
        self, organization_id: UUID, workspace_id: UUID, payload: ChatbotInput
    ) -> Chatbot:
        await self._workspace(organization_id, workspace_id)
        chatbot = Chatbot(
            organization_id=organization_id,
            workspace_id=workspace_id,
            name=payload.name.strip(),
            system_prompt=payload.system_prompt.strip(),
            model=payload.model,
            retrieval_limit=payload.retrieval_limit,
            published=payload.published,
        )
        self.session.add(chatbot)
        await self.session.commit()
        await self.session.refresh(chatbot)
        return chatbot

    async def get(self, organization_id: UUID, chatbot_id: UUID) -> Chatbot:
        chatbot = await self.session.scalar(
            select(Chatbot).where(
                Chatbot.id == chatbot_id, Chatbot.organization_id == organization_id
            )
        )
        if chatbot is None:
            raise AppError(
                "CHATBOT_NOT_FOUND",
                "Chatbot was not found in the current organization.",
                status_code=404,
            )
        return chatbot

    async def update(
        self, organization_id: UUID, chatbot_id: UUID, payload: ChatbotPatch
    ) -> Chatbot:
        chatbot = await self.get(organization_id, chatbot_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(chatbot, field, value.strip() if isinstance(value, str) else value)
        await self.session.commit()
        await self.session.refresh(chatbot)
        return chatbot

    async def delete(self, organization_id: UUID, chatbot_id: UUID) -> None:
        await self.session.delete(await self.get(organization_id, chatbot_id))
        await self.session.commit()

    async def publish_embed(
        self, organization_id: UUID, chatbot_id: UUID, payload: EmbedPublishInput
    ) -> tuple[Chatbot, str | None]:
        chatbot = await self.get(organization_id, chatbot_id)
        raw_key: str | None = None
        if not chatbot.embed_key_hash:
            raw_key, chatbot.embed_key_hash = create_embed_key()
        chatbot.published = True
        chatbot.allowed_origins = [origin.rstrip("/") for origin in payload.allowed_origins]
        chatbot.embed_primary_color = payload.primary_color
        chatbot.embed_title = payload.title.strip()
        chatbot.embed_greeting = payload.greeting.strip()
        await self.session.commit()
        await self.session.refresh(chatbot)
        return chatbot, raw_key

    async def rotate_embed_key(self, organization_id: UUID, chatbot_id: UUID) -> str:
        chatbot = await self.get(organization_id, chatbot_id)
        raw_key, chatbot.embed_key_hash = create_embed_key()
        await self.session.commit()
        return raw_key

    async def public_chatbot(self, raw_key: str, origin: str | None) -> Chatbot:
        chatbot = await self.session.scalar(
            select(Chatbot).where(Chatbot.embed_key_hash == hash_embed_key(raw_key))
        )
        if chatbot is None or not chatbot.published:
            raise AppError(
                "EMBED_CHATBOT_NOT_FOUND", "This chatbot is unavailable.", status_code=404
            )
        if not origin_is_allowed(origin, chatbot.allowed_origins):
            raise AppError(
                "EMBED_ORIGIN_NOT_ALLOWED", "This website is not allowed.", status_code=403
            )
        return chatbot

    async def public_config(self, raw_key: str, origin: str | None) -> dict[str, str]:
        return public_config(await self.public_chatbot(raw_key, origin))

    async def _conversation(self, chatbot, conversation_id, external_user_id):
        return await ConversationRepositoryAdapter(self.session)._conversation(
            chatbot,
            conversation_id,
            external_user_id,
        )

    async def _history(self, conversation_id: UUID) -> list[dict[str, str]]:
        return await ConversationRepositoryAdapter(self.session)._history(conversation_id)

    async def stream_events(self, command: StreamChatCommand) -> AsyncIterator[RagEvent]:
        use_case = rag_use_case(
            self.session,
            self.get,
            self._conversation,
            self._history,
            lambda: SearchService(self.session),
            lambda: ProviderResolver(self.session),
        )
        async with aclosing(use_case.execute(command)) as stream:
            async for event in stream:
                yield event

    async def stream(
        self,
        organization_id: UUID,
        chatbot_id: UUID,
        question: str,
        conversation_id: UUID | None,
        external_user_id: str | None,
    ):
        """Compatibility event tuples; new delivery uses stream_events."""
        async for event in self.stream_events(
            StreamChatCommand(
                organization_id,
                chatbot_id,
                question,
                conversation_id,
                external_user_id,
            )
        ):
            yield event_payload(event)
