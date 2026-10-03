from dataclasses import dataclass
from uuid import UUID

from app.core_domain.ingestion.chunker import TextChunk


@dataclass(frozen=True)
class RetrievalScope:
    organization_id: UUID
    workspace_id: UUID


@dataclass(frozen=True)
class RetrievedChunk:
    document_id: UUID
    document_version_id: UUID
    chunk_id: UUID
    content: str
    source_name: str
    page_number: int | None
    heading: str | None
    score: float


@dataclass(frozen=True)
class IndexedChunk:
    chunk: TextChunk
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class DocumentIndex:
    scope: RetrievalScope
    document_id: UUID
    document_version_id: UUID
    source_name: str
    chunks: tuple[IndexedChunk, ...]
