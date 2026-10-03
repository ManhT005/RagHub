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

    def as_payload(self) -> dict[str, object]:
        return {
            "citation_id": self.citation_id,
            "document_id": str(self.document_id),
            "document_name": self.document_name,
            "page": self.page,
            "chunk_id": str(self.chunk_id),
            "excerpt": self.excerpt,
            "score": self.score,
        }


@dataclass(frozen=True)
class ChatUsageRecord:
    scope: RetrievalScope
    message_id: UUID
    provider: str
    model: str
    usage: ChatUsage
    first_token_ms: int | None
    latency_ms: int
