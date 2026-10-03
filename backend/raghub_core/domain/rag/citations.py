from collections.abc import Iterable

from raghub_core.domain.rag.models import TrustedCitation
from raghub_core.domain.retrieval.models import RetrievedChunk


def resolve_trusted_citations(hits: Iterable[RetrievedChunk]) -> tuple[TrustedCitation, ...]:
    return tuple(
        TrustedCitation(
            citation_id=f"C{rank}",
            document_id=hit.document_id,
            document_name=hit.source_name,
            page=hit.page_number,
            chunk_id=hit.chunk_id,
            excerpt=hit.content[:500],
            score=hit.score,
        )
        for rank, hit in enumerate(hits, start=1)
    )
