from collections.abc import Iterable
from dataclasses import dataclass, replace
from uuid import UUID

from app.core_domain.ingestion.tokenizer import ENCODING
from app.core_domain.retrieval.models import RetrievedChunk

RETRIEVAL_CANDIDATES = 15
RRF_K = 60
MAX_CONTEXT_TOKENS = 6000


@dataclass(frozen=True)
class ContextBundle:
    text: str
    hits: list[RetrievedChunk]


def fuse_rrf(
    rankings: Iterable[list[RetrievedChunk]], *, limit: int, rrf_k: int = RRF_K
) -> list[RetrievedChunk]:
    """Merge ranked result lists with Reciprocal Rank Fusion."""
    merged: dict[UUID, RetrievedChunk] = {}
    scores: dict[UUID, float] = {}
    first_seen: dict[UUID, int] = {}
    sequence = 0
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            chunk_id = hit.chunk_id
            if chunk_id not in merged:
                merged[chunk_id] = hit
                first_seen[chunk_id] = sequence
                sequence += 1
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (rrf_k + rank)
    ordered_ids = sorted(
        merged,
        key=lambda chunk_id: (-scores[chunk_id], first_seen[chunk_id]),
    )
    return [replace(merged[chunk_id], score=scores[chunk_id]) for chunk_id in ordered_ids[:limit]]


def build_context_bundle(
    hits: Iterable[RetrievedChunk], *, max_tokens: int = MAX_CONTEXT_TOKENS
) -> ContextBundle:
    """Build context and retain exactly the chunks represented in its text."""
    parts: list[str] = []
    selected: list[RetrievedChunk] = []
    for index, hit in enumerate(hits, start=1):
        citation = f"[C{index}]\nsource: {hit.source_name}"
        if hit.page_number is not None:
            citation += f"\npage: {hit.page_number}"
        citation += f"\nchunk_id: {hit.chunk_id}"
        if hit.heading:
            citation += f"\nheading: {hit.heading}"
        candidate = f"{citation}\ncontent:\n{hit.content}"
        proposed = "\n\n".join([*parts, candidate])
        tokens = ENCODING.encode(proposed)
        if len(tokens) <= max_tokens:
            parts.append(candidate)
            selected.append(hit)
        elif not parts and max_tokens:
            parts.append(ENCODING.decode(tokens[:max_tokens]))
            selected.append(hit)
            break
        else:
            break
    return ContextBundle(text="\n\n".join(parts), hits=selected)


def build_context(hits: Iterable[RetrievedChunk], *, max_tokens: int = MAX_CONTEXT_TOKENS) -> str:
    """Compatibility helper for search clients that only need rendered context."""
    return build_context_bundle(hits, max_tokens=max_tokens).text
