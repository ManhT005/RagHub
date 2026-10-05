from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import aclosing
from uuid import UUID

from raghub_core.domain.chatbots.models import CreateChatbotCommand, PatchChatbotCommand
from raghub_core.domain.rag.events import RagEvent
from raghub_core.domain.rag.models import StreamChatCommand
from raghub_core.domain.rag.prompt import EMPTY_CONTEXT_ANSWER as EMPTY_CONTEXT_ANSWER
from raghub_core.domain.retrieval.models import RetrievalScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.public_chat import PublicChatContainer
from app.composition.self_host import SelfHostContainer
from app.infrastructure.persistence.conversations import ConversationRepositoryAdapter
from app.modules.chatbots.embed import (
    create_embed_key,
    public_config,
)
from app.modules.chatbots.models import Chatbot
from app.modules.chatbots.schemas import ChatbotInput, ChatbotPatch, EmbedPublishInput


class ChatbotService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.container = SelfHostContainer(session)

    async def list(self, organization_id: UUID, workspace_id: UUID):
        records = await self.container.manage_chatbots().list(
            RetrievalScope(organization_id, workspace_id)
        )
        return [await self._entity(organization_id, record.id) for record in records]

    async def _entity(self, organization_id: UUID, chatbot_id: UUID):
        # Preserve delivery-only embed settings on the legacy HTTP facade.
        return await self.container.chatbots._get(organization_id, chatbot_id)

    async def create(self, organization_id: UUID, workspace_id: UUID, payload: ChatbotInput):
        record = await self.container.manage_chatbots().create(
            CreateChatbotCommand(
                RetrievalScope(organization_id, workspace_id),
                **payload.model_dump(),
            )
        )
        return await self._entity(organization_id, record.id)

    async def get(self, organization_id: UUID, chatbot_id: UUID):
        await self.container.manage_chatbots().get(organization_id, chatbot_id)
        return await self._entity(organization_id, chatbot_id)

    async def update(self, organization_id: UUID, chatbot_id: UUID, payload: ChatbotPatch):
        record = await self.container.manage_chatbots().update(
            organization_id,
            chatbot_id,
            PatchChatbotCommand(**payload.model_dump(exclude_unset=True)),
        )
        return await self._entity(organization_id, record.id)

    async def delete(self, organization_id: UUID, chatbot_id: UUID) -> None:
        await self.container.manage_chatbots().delete(organization_id, chatbot_id)

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
        return await PublicChatContainer(self.session).resolve(raw_key, origin)

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
        use_case = self.container.stream_chat(
            chatbot_loader=self.get,
            conversation_loader=self._conversation,
            history_loader=self._history,
        )
        async with aclosing(use_case.execute(command)) as stream:
            async for event in stream:
                yield event
