"""Raw search conversion belongs to the infrastructure boundary."""

from uuid import UUID

from raghub_core.domain.retrieval.hybrid import RRF_K, fuse_rrf_with_details
from raghub_core.domain.retrieval.models import RetrievalCandidate, RetrievedChunk


def chunk_from_hit(hit: dict[str, object]) -> RetrievedChunk:
    return RetrievedChunk(
        UUID(str(hit["document_id"])),
        UUID(str(hit["document_version_id"])),
        UUID(str(hit["chunk_id"])),
        str(hit.get("raw_content", hit["content"])),
        str(hit["source_name"]),
        hit.get("page_number"),
        hit.get("heading"),
        float(hit["score"]),
        hit.get("chunk_index"),
        normalized_content=str(hit.get("normalized_content", hit["content"]))
        if "raw_content" in hit
        else None,
        heading_path=tuple(hit.get("heading_path") or ()),
        parent_section_id=UUID(str(hit["parent_section_id"]))
        if hit.get("parent_section_id")
        else None,
        previous_chunk_id=UUID(str(hit["previous_chunk_id"]))
        if hit.get("previous_chunk_id")
        else None,
        next_chunk_id=UUID(str(hit["next_chunk_id"])) if hit.get("next_chunk_id") else None,
        metadata=hit.get("metadata") or {},
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
        **({"chunk_index": hit.chunk_index} if hit.chunk_index is not None else {}),
        "document_id": str(hit.document_id),
        "document_version_id": str(hit.document_version_id),
        "chunk_id": str(hit.chunk_id),
        "content": hit.content,
        "source_name": hit.source_name,
        "page_number": hit.page_number,
        "heading": hit.heading,
        "score": hit.score,
        **(
            {"raw_content": hit.content, "normalized_content": hit.normalized_content}
            if hit.normalized_content is not None
            else {}
        ),
        **({"heading_path": list(hit.heading_path)} if hit.heading_path else {}),
        **({"parent_section_id": str(hit.parent_section_id)} if hit.parent_section_id else {}),
        **({"previous_chunk_id": str(hit.previous_chunk_id)} if hit.previous_chunk_id else {}),
        **({"next_chunk_id": str(hit.next_chunk_id)} if hit.next_chunk_id else {}),
        **({"metadata": dict(hit.metadata)} if hit.metadata else {}),
    }
