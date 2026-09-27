from collections.abc import Iterable
from typing import Any


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
