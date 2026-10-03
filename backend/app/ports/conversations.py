from typing import Protocol
from uuid import UUID

from app.core_domain.chatbots.models import ChatbotConfig
from app.core_domain.providers.contracts import ChatMessage, ChatUsage
from app.core_domain.rag.models import TrustedCitation


class ConversationRepositoryPort(Protocol):
    """Writes are staged; the use case chooses when to commit a turn.

    History is requested before add_user and excludes failed assistant messages.
    """
    async def open(
        self, chatbot: ChatbotConfig, conversation_id: UUID | None, external_user_id: str | None
    ) -> UUID: ...
    async def add_user(self, conversation_id: UUID, content: str) -> UUID: ...
    async def history(self, conversation_id: UUID) -> list[ChatMessage]: ...
    async def add_assistant(
        self,
        conversation_id: UUID,
        content: str,
        usage: ChatUsage,
        citations: tuple[TrustedCitation, ...],
    ) -> UUID: ...
    async def add_failed_assistant(
        self, conversation_id: UUID, content: str, error_code: str
    ) -> UUID: ...
    async def commit(self) -> None: ...
