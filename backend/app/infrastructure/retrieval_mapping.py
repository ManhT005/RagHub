"""Raw search conversion belongs to the infrastructure boundary."""

from uuid import UUID

from raghub_core.domain.retrieval.hybrid import RRF_K, fuse_rrf_with_details
from raghub_core.domain.retrieval.models import RetrievalCandidate, RetrievedChunk


def chunk_from_hit(hit: dict[str, object]) -> RetrievedChunk:
    return RetrievedChunk(
        UUID(str(hit["document_id"])),
        UUID(str(hit["document_version_id"])),
        UUID(str(hit["chunk_id"])),
        str(hit["content"]),
        str(hit["source_name"]),
        hit.get("page_number"),
        hit.get("heading"),
        float(hit["score"]),
    )


def fuse_branches_to_candidates(
    lexical: list[dict[str, object]],
    vector: list[dict[str, object]],
    *,
    limit: int,
    rrf_k: int = RRF_K,
) -> list[RetrievalCandidate]:
    """Build explainable candidates from raw per-branch hits (lexical first)."""
    return fuse_rrf_with_details(
        [[chunk_from_hit(hit) for hit in lexical], [chunk_from_hit(hit) for hit in vector]],
        limit=limit,
        rrf_k=rrf_k,
    )


def chunk_to_hit(hit: RetrievedChunk) -> dict[str, object]:
    return {
        "document_id": str(hit.document_id),
        "document_version_id": str(hit.document_version_id),
        "chunk_id": str(hit.chunk_id),
        "content": hit.content,
        "source_name": hit.source_name,
        "page_number": hit.page_number,
        "heading": hit.heading,
        "score": hit.score,
    }
