from collections.abc import Iterable
from typing import Any
from uuid import UUID

from app.core_domain.rag.models import TrustedCitation
from app.core_domain.retrieval.models import RetrievedChunk


def resolve_citations(hits: Iterable[dict[str, Any]]) -> list[dict[str, object]]:
    """Create trusted citation metadata exclusively from selected backend hits."""
    return [
        {
            "citation_id": f"C{rank}",
            "document_id": str(hit["document_id"]),
            "document_name": str(hit["source_name"]),
            "page": hit.get("page_number"),
            "chunk_id": str(hit["chunk_id"]),
            "excerpt": str(hit["content"])[:500],
            "score": float(hit["score"]),
        }
        for rank, hit in enumerate(hits, start=1)
    ]


def resolve_trusted_citations(hits: Iterable[RetrievedChunk]) -> tuple[TrustedCitation, ...]:
    return tuple(
        TrustedCitation(
            citation_id=citation["citation_id"],
            document_id=UUID(citation["document_id"]),
            document_name=citation["document_name"],
            page=citation["page"],
            chunk_id=UUID(citation["chunk_id"]),
            excerpt=citation["excerpt"],
            score=citation["score"],
        )
        for citation in resolve_citations(hit.as_hit() for hit in hits)
    )
