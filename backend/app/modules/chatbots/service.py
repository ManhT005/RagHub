from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import aclosing
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.chatbots import chatbot_management
from app.composition.rag import rag_use_case
from app.core_domain.chatbots.models import CreateChatbotCommand, PatchChatbotCommand
from app.core_domain.rag.events import RagEvent
from app.core_domain.rag.models import StreamChatCommand
from app.core_domain.rag.prompt import EMPTY_CONTEXT_ANSWER as EMPTY_CONTEXT_ANSWER
from app.core_domain.retrieval.models import RetrievalScope
from app.delivery.http.sse import event_payload
from app.infrastructure.persistence.conversations import ConversationRepositoryAdapter
from app.modules.ai_providers.resolver import ProviderResolver
from app.modules.chatbots.schemas import ChatbotInput, ChatbotPatch
from app.modules.search.service import SearchService


class ChatbotService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, organization_id: UUID, workspace_id: UUID):
        return await chatbot_management(self.session).list(
            RetrievalScope(organization_id, workspace_id)
        )

    async def create(self, organization_id: UUID, workspace_id: UUID, payload: ChatbotInput):
        return await chatbot_management(self.session).create(
            CreateChatbotCommand(
                RetrievalScope(organization_id, workspace_id),
                **payload.model_dump(),
            )
        )

    async def get(self, organization_id: UUID, chatbot_id: UUID):
        return await chatbot_management(self.session).get(organization_id, chatbot_id)

    async def update(self, organization_id: UUID, chatbot_id: UUID, payload: ChatbotPatch):
        return await chatbot_management(self.session).update(
            organization_id,
            chatbot_id,
            PatchChatbotCommand(**payload.model_dump(exclude_unset=True)),
        )

    async def delete(self, organization_id: UUID, chatbot_id: UUID) -> None:
        await chatbot_management(self.session).delete(organization_id, chatbot_id)

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
