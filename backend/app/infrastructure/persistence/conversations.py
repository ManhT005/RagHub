from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core_domain.errors import CoreError
from app.core_domain.providers.contracts import ChatMessage, ChatUsage
from app.core_domain.rag.models import ChatUsageRecord, TrustedCitation
from app.modules.chatbots.models import Chatbot, Conversation, Message, MessageCitation, UsageEvent


class ConversationRepositoryAdapter:
    def __init__(
        self, session: AsyncSession, *, conversation_loader=None, history_loader=None
    ) -> None:
        self.session = session
        self.conversation_loader = conversation_loader or self._conversation
        self.history_loader = history_loader or self._history

    async def _conversation(
        self, chatbot: Chatbot, conversation_id: UUID | None, external_user_id: str | None
    ) -> Conversation:
        if conversation_id:
            conversation = await self.session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id, Conversation.chatbot_id == chatbot.id
                )
            )
            if conversation is None:
                raise CoreError(
                    "CONVERSATION_NOT_FOUND",
                    "Conversation does not belong to this chatbot.",
                )
            if conversation.external_user_id != external_user_id:
                raise CoreError(
                    "CONVERSATION_ACCESS_DENIED",
                    "Conversation does not belong to this user.",
                )
            return conversation
        conversation = Conversation(chatbot_id=chatbot.id, external_user_id=external_user_id)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def _history(self, conversation_id: UUID) -> list[dict[str, str]]:
        messages = list(
            (
                await self.session.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation_id,
                        Message.usage_json["status"].as_string().is_distinct_from("FAILED"),
                    )
                    .order_by(Message.created_at.desc())
                    .limit(12)
                )
            ).all()
        )
        return [
            {"role": message.role, "content": message.content} for message in reversed(messages)
        ]

    async def open(self, chatbot, conversation_id, external_user_id) -> UUID:
        conversation = await self.conversation_loader(chatbot, conversation_id, external_user_id)
        return conversation.id

    async def add_user(self, conversation_id: UUID, content: str) -> UUID:
        message = Message(
            conversation_id=conversation_id, role="user", content=content, usage_json=None
        )
        self.session.add(message)
        await self.session.flush()
        return message.id

    async def add_failed_assistant(
        self, conversation_id: UUID, content: str, error_code: str
    ) -> UUID:
        message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            usage_json={"status": "FAILED", "error_code": error_code},
        )
        self.session.add(message)
        await self.session.flush()
        return message.id

    async def history(self, conversation_id: UUID) -> list[ChatMessage]:
        return [ChatMessage(**message) for message in await self.history_loader(conversation_id)]

    async def add_assistant(
        self,
        conversation_id: UUID,
        content: str,
        usage: ChatUsage,
        citations: tuple[TrustedCitation, ...],
    ) -> UUID:
        message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            usage_json=asdict(usage),
        )
        self.session.add(message)
        await self.session.flush()
        for rank, citation in enumerate(citations, 1):
            self.session.add(
                MessageCitation(
                    message_id=message.id,
                    document_id=citation.document_id,
                    chunk_id=citation.chunk_id,
                    document_name=citation.document_name,
                    page_number=citation.page,
                    excerpt=citation.excerpt,
                    rank=rank,
                    score=citation.score,
                )
            )
        return message.id

    async def commit(self) -> None:
        await self.session.commit()


class UsageRecorderAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_chat_usage(self, record: ChatUsageRecord) -> None:
        self.session.add(
            UsageEvent(
                organization_id=record.scope.organization_id,
                message_id=record.message_id,
                provider=record.provider,
                model=record.model,
                prompt_tokens=record.usage.prompt_tokens,
                completion_tokens=record.usage.completion_tokens,
                first_token_ms=record.first_token_ms,
                latency_ms=record.latency_ms,
            )
        )
