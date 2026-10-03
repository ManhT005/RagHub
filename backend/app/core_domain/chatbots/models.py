from dataclasses import dataclass
from datetime import datetime
from enum import Enum
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


@dataclass(frozen=True)
class ChatbotRecord:
    id: UUID
    organization_id: UUID
    workspace_id: UUID
    name: str
    system_prompt: str
    model: str | None
    retrieval_limit: int
    published: bool
    created_at: datetime
    updated_at: datetime | None

    @property
    def scope(self) -> RetrievalScope:
        return RetrievalScope(self.organization_id, self.workspace_id)


@dataclass(frozen=True)
class CreateChatbotCommand:
    scope: RetrievalScope
    name: str
    system_prompt: str = ""
    model: str | None = None
    retrieval_limit: int = 5
    published: bool = False


class Unset(Enum):
    VALUE = "unset"


@dataclass(frozen=True)
class PatchChatbotCommand:
    name: str | None | Unset = Unset.VALUE
    system_prompt: str | None | Unset = Unset.VALUE
    model: str | None | Unset = Unset.VALUE
    retrieval_limit: int | None | Unset = Unset.VALUE
    published: bool | None | Unset = Unset.VALUE
