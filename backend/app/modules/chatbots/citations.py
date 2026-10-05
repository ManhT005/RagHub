"""Compatibility payloads are mapped outside the engine."""

from app.infrastructure.retrieval_mapping import chunk_from_hit
from raghub_core.domain.rag.citations import resolve_trusted_citations


def resolve_citations(hits):
    return [
        {
            "citation_id": c.citation_id,
            "document_id": str(c.document_id),
            "document_name": c.document_name,
            "page": c.page,
            "chunk_id": str(c.chunk_id),
            "excerpt": c.excerpt,
            "score": c.score,
        }
        for c in resolve_trusted_citations(chunk_from_hit(hit) for hit in hits)
    ]
