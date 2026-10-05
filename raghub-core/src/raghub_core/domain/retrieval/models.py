from dataclasses import dataclass
from uuid import UUID

from raghub_core.domain.ingestion.chunker import TextChunk


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
class RetrievalCandidate:
    """Internal explainability record: per-branch scores/ranks plus fusion outcome.

    Never threshold raw BM25/vector/RRF scores across queries; calibration
    (Phase 5) consumes fused rank/score distributions, not raw values.
    """

    chunk: RetrievedChunk
    bm25_score: float | None
    bm25_rank: int | None
    vector_score: float | None
    vector_rank: int | None
    fused_score: float
    fused_rank: int
    reranker_score: float | None = None
    confidence: float | None = None

    @property
    def in_bm25(self) -> bool:
        return self.bm25_rank is not None

    @property
    def in_vector(self) -> bool:
        return self.vector_rank is not None


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
