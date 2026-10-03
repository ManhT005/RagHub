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

    def as_hit(self) -> dict[str, object]:
        return {
            "document_id": str(self.document_id),
            "document_version_id": str(self.document_version_id),
            "chunk_id": str(self.chunk_id), "content": self.content,
            "source_name": self.source_name, "page_number": self.page_number,
            "heading": self.heading, "score": self.score,
        }

    @classmethod
    def from_hit(cls, hit: dict[str, object]) -> "RetrievedChunk":
        return cls(
            document_id=UUID(str(hit["document_id"])),
            document_version_id=UUID(str(hit["document_version_id"])),
            chunk_id=UUID(str(hit["chunk_id"])), content=str(hit["content"]),
            source_name=str(hit["source_name"]), page_number=hit.get("page_number"),
            heading=hit.get("heading"), score=float(hit["score"]),
        )


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
