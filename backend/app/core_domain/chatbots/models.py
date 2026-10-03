from dataclasses import dataclass
from uuid import UUID

from app.core_domain.retrieval.models import RetrievalScope


@dataclass(frozen=True)
class ChatbotConfig:
    id: UUID
    scope: RetrievalScope
    name: str
    system_prompt: str
    retrieval_limit: int
    published: bool
    model: str | None = None
