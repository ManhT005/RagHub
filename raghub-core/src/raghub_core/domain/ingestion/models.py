from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from raghub_core.domain.retrieval.models import RetrievalScope


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
    kind: str = "upload"


@dataclass(frozen=True)
class IngestionAttempt:
    document: IngestionDocument | None
    status: str
    progress: int
    reason: str | None = None


@dataclass(frozen=True)
class IngestionResult:
    version_id: UUID
    status: str
    processed: bool
    reason: str | None = None
