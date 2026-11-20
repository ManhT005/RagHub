from dataclasses import dataclass
from uuid import UUID

from raghub_core.domain.providers.contracts import ChatUsage
from raghub_core.domain.retrieval.models import RetrievalScope


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
    # Exact text made available to the model for this citation. This is kept
    # separate from the short excerpt stored with conversation history.
    chunk_content: str
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
