from dataclasses import dataclass
from uuid import UUID

from app.core_domain.providers.contracts import ChatUsage
from app.core_domain.rag.models import TrustedCitation


@dataclass(frozen=True)
class ConversationStarted:
    conversation_id: UUID
    user_message_id: UUID


@dataclass(frozen=True)
class CitationsResolved:
    citations: tuple[TrustedCitation, ...]


@dataclass(frozen=True)
class TokenDelta:
    text: str


@dataclass(frozen=True)
class UsageReported:
    usage: ChatUsage


@dataclass(frozen=True)
class ChatCompleted:
    message_id: UUID
    first_token_ms: int | None
    latency_ms: int


@dataclass(frozen=True)
class ChatFailed:
    code: str
    message: str


RagEvent = (
    ConversationStarted
    | CitationsResolved
    | TokenDelta
    | UsageReported
    | ChatCompleted
    | ChatFailed
)
