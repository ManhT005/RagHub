from dataclasses import dataclass
from uuid import UUID

from app.core_domain.providers.contracts import ChatUsage
from app.core_domain.retrieval.models import RetrievalScope


@dataclass(frozen=True)
class StreamChatCommand:
    organization_id: UUID
    chatbot_id: UUID
    question: str
    conversation_id: UUID | None = None
    external_user_id: str | None = None


@dataclass(frozen=True)
class TrustedCitation:
    citation_id: str
    document_id: UUID
    document_name: str
    page: int | None
    chunk_id: UUID
    excerpt: str
    score: float


@dataclass(frozen=True)
class ChatUsageRecord:
    scope: RetrievalScope
    message_id: UUID
    provider: str
    model: str
    usage: ChatUsage
    first_token_ms: int | None
    latency_ms: int
