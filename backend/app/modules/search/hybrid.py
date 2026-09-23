from collections.abc import Iterable
from typing import Any

from app.modules.ingestion.tokenizer import ENCODING

RETRIEVAL_CANDIDATES = 15
RRF_K = 60
MAX_CONTEXT_TOKENS = 6000


def fuse_rrf(
    rankings: Iterable[list[dict[str, Any]]], *, limit: int, rrf_k: int = RRF_K
) -> list[dict[str, Any]]:
    """Merge ranked result lists with Reciprocal Rank Fusion."""
    merged: dict[str, dict[str, Any]] = {}
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    sequence = 0
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            chunk_id = str(hit["chunk_id"])
            if chunk_id not in merged:
                merged[chunk_id] = hit
                first_seen[chunk_id] = sequence
                sequence += 1
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (rrf_k + rank)
    ordered_ids = sorted(
        merged,
        key=lambda chunk_id: (-scores[chunk_id], first_seen[chunk_id]),
    )
    return [{**merged[chunk_id], "score": scores[chunk_id]} for chunk_id in ordered_ids[:limit]]


def build_context(hits: Iterable[dict[str, Any]], *, max_tokens: int = MAX_CONTEXT_TOKENS) -> str:
    """Create citation-ready RAG context without exceeding the token budget."""
    remaining = max_tokens
    parts: list[str] = []
    for hit in hits:
        citation = f"[chunk_id={hit['chunk_id']}; source={hit['source_name']}"
        if hit.get("page_number") is not None:
            citation += f"; page={hit['page_number']}"
        if hit.get("heading"):
            citation += f"; heading={hit['heading']}"
        citation += "]"
        candidate = f"{citation}\n{hit['content']}"
        tokens = ENCODING.encode(candidate)
        if len(tokens) <= remaining:
            parts.append(candidate)
            remaining -= len(tokens)
        elif remaining:
            parts.append(ENCODING.decode(tokens[:remaining]))
            remaining = 0
        if not remaining:
            break
    return "\n\n".join(parts)
