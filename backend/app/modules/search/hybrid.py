"""HTTP compatibility mapping; the engine consumes only RetrievedChunk DTOs."""

from dataclasses import dataclass

from app.core_domain.retrieval.hybrid import MAX_CONTEXT_TOKENS
from app.core_domain.retrieval.hybrid import RETRIEVAL_CANDIDATES as RETRIEVAL_CANDIDATES
from app.core_domain.retrieval.hybrid import RRF_K as RRF_K
from app.core_domain.retrieval.hybrid import build_context_bundle as typed_context
from app.core_domain.retrieval.hybrid import fuse_rrf as typed_rrf
from app.infrastructure.retrieval_mapping import chunk_from_hit, chunk_to_hit


@dataclass(frozen=True)
class ContextBundle:
    text: str
    hits: list[dict[str, object]]


def fuse_rrf(rankings, *, limit, rrf_k=RRF_K):
    return [
        chunk_to_hit(hit)
        for hit in typed_rrf(
            [[chunk_from_hit(hit) for hit in ranking] for ranking in rankings],
            limit=limit,
            rrf_k=rrf_k,
        )
    ]


def build_context_bundle(hits, *, max_tokens=MAX_CONTEXT_TOKENS):
    bundle = typed_context((chunk_from_hit(hit) for hit in hits), max_tokens=max_tokens)
    return ContextBundle(bundle.text, [chunk_to_hit(hit) for hit in bundle.hits])


def build_context(hits, *, max_tokens=MAX_CONTEXT_TOKENS):
    return build_context_bundle(hits, max_tokens=max_tokens).text
