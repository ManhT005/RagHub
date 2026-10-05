import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, replace
from uuid import UUID

from raghub_core.domain.ingestion.tokenizer import ENCODING
from raghub_core.domain.retrieval.models import RetrievalCandidate, RetrievedChunk

RETRIEVAL_CANDIDATES = 25
RETRIEVAL_CANDIDATES_MIN = 10
RETRIEVAL_CANDIDATES_MAX = 100
RERANK_SOURCE_COUNT = 25
RERANK_TOP_N = 8
RRF_K = 60
MAX_CONTEXT_TOKENS = 6000
MAPPING_VERSION = "vi_hybrid_v2"


def normalize_query(query: str) -> str:
    """Unicode NFC + trim + collapse whitespace. Never strip diacritics."""
    text = unicodedata.normalize("NFC", query or "")
    return " ".join(text.split())


def resolve_candidate_count(value: int | None) -> int:
    """Clamp/validate the per-branch candidate count into the 10-100 window."""
    if value is None:
        return RETRIEVAL_CANDIDATES
    count = int(value)
    if not RETRIEVAL_CANDIDATES_MIN <= count <= RETRIEVAL_CANDIDATES_MAX:
        raise ValueError(
            f"Candidate count must be within {RETRIEVAL_CANDIDATES_MIN}-"
            f"{RETRIEVAL_CANDIDATES_MAX}, got {value}."
        )
    return count


@dataclass(frozen=True)
class ContextBundle:
    text: str
    hits: list[RetrievedChunk]


def fuse_rrf(
    rankings: Iterable[list[RetrievedChunk]], *, limit: int, rrf_k: int = RRF_K
) -> list[RetrievedChunk]:
    """Merge ranked result lists with Reciprocal Rank Fusion."""
    return [
        candidate.chunk
        for candidate in fuse_rrf_with_details(rankings, limit=limit, rrf_k=rrf_k)
    ]


def fuse_rrf_with_details(
    rankings: Iterable[list[RetrievedChunk]], *, limit: int, rrf_k: int = RRF_K
) -> list[RetrievalCandidate]:
    """RRF merge keeping per-branch raw score/rank and presence flags."""
    lists = [list(ranking) for ranking in rankings]
    branch_rank: list[dict[UUID, int]] = []
    branch_score: list[dict[UUID, float]] = []
    merged: dict[UUID, RetrievedChunk] = {}
    first_seen: dict[UUID, int] = {}
    sequence = 0
    for ranking in lists:
        ranks: dict[UUID, int] = {}
        scores: dict[UUID, float] = {}
        for rank, hit in enumerate(ranking, start=1):
            chunk_id = hit.chunk_id
            ranks[chunk_id] = rank
            scores[chunk_id] = hit.score
            if chunk_id not in merged:
                merged[chunk_id] = hit
                first_seen[chunk_id] = sequence
                sequence += 1
        branch_rank.append(ranks)
        branch_score.append(scores)
    fused: dict[UUID, float] = {}
    for ranks in branch_rank:
        for chunk_id, rank in ranks.items():
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1 / (rrf_k + rank)
    ordered_ids = sorted(
        merged,
        key=lambda chunk_id: (-fused[chunk_id], first_seen[chunk_id]),
    )[:limit]

    def first_hit(maps: list[dict[UUID, float]], chunk_id: UUID) -> float | None:
        for mapping in maps:
            if chunk_id in mapping:
                return mapping[chunk_id]
        return None

    def first_rank(maps: list[dict[UUID, int]], chunk_id: UUID) -> int | None:
        for mapping in maps:
            if chunk_id in mapping:
                return mapping[chunk_id]
        return None

    # Branch 0 is BM25, remaining branches are vector by convention.
    candidates = [
        RetrievalCandidate(
            chunk=replace(merged[chunk_id], score=fused[chunk_id]),
            bm25_score=first_hit(branch_score[:1], chunk_id),
            bm25_rank=first_rank(branch_rank[:1], chunk_id),
            vector_score=first_hit(branch_score[1:], chunk_id),
            vector_rank=first_rank(branch_rank[1:], chunk_id),
            fused_score=fused[chunk_id],
            fused_rank=rank + 1,
        )
        for rank, chunk_id in enumerate(ordered_ids)
    ]
    return candidates


def render_citation_block(index: int, hit: RetrievedChunk, content: str | None = None) -> str:
    """Render one [Cn] block; an explicit content override renders a budget slice."""
    citation = f"[C{index}]\nsource: {hit.source_name}"
    if hit.page_number is not None:
        citation += f"\npage: {hit.page_number}"
    citation += f"\nchunk_id: {hit.chunk_id}"
    if hit.heading:
        citation += f"\nheading: {hit.heading}"
    return f"{citation}\ncontent:\n{content if content is not None else hit.content}"


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
