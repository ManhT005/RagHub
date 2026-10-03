from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.core_domain.retrieval.models import RetrievalScope


class IngestionStage(StrEnum):
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"


@dataclass(frozen=True)
class IngestionDocument:
    scope: RetrievalScope
    document_id: UUID
    version_id: UUID
    storage_key: str
    source_name: str


@dataclass(frozen=True)
class IngestionAttempt:
    document: IngestionDocument
    status: str
    progress: int


@dataclass(frozen=True)
class IngestionResult:
    version_id: UUID
    status: str
    processed: bool
