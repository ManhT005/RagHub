from collections.abc import Iterable, Sequence

from raghub_core.domain.rag.models import TrustedCitation
from raghub_core.domain.retrieval.hybrid import ContextBundle, render_citation_block
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


def resolve_sliced_citations(
    hits: Sequence[RetrievedChunk], slices: Sequence[tuple[int, str]]
) -> tuple[TrustedCitation, ...]:
    """Citation inventory mirrors exactly the sent slices (index, slice text).

    A chunk dropped by the budgeter never appears in the inventory, and a
    truncated first chunk is excerpted from the sent slice, not the full text.
    """
    resolved: list[TrustedCitation] = []
    for rank, (position, text) in enumerate(slices, start=1):
        hit = hits[position]
        resolved.append(
            TrustedCitation(
                citation_id=f"C{rank}",
                document_id=hit.document_id,
                document_name=hit.source_name,
                page=hit.page_number,
                chunk_id=hit.chunk_id,
                excerpt=text[:500],
                score=hit.score,
            )
        )
    return tuple(resolved)


def render_sliced_bundle(
    hits: Sequence[RetrievedChunk], slices: Sequence[tuple[int, str]]
) -> ContextBundle:
    """Render budgeted slices with stable [Cn] ranks; no second truncation."""
    parts = [
        render_citation_block(rank, hits[position], text)
        for rank, (position, text) in enumerate(slices, start=1)
    ]
    selected = [
        RetrievedChunk(
            document_id=hits[position].document_id,
            document_version_id=hits[position].document_version_id,
            chunk_id=hits[position].chunk_id,
            content=text,
            source_name=hits[position].source_name,
            page_number=hits[position].page_number,
            heading=hits[position].heading,
            score=hits[position].score,
        )
        for position, text in slices
    ]
    return ContextBundle(text="\n\n".join(parts), hits=selected)
