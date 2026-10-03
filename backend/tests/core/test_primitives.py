from uuid import uuid4

import pytest

from raghub_core.domain.ingestion.chunker import chunk_sections
from raghub_core.domain.ingestion.parser import ParsedSection, parse_document
from raghub_core.domain.providers.contracts import ChatMessage
from raghub_core.domain.providers.usage import estimate_chat_usage
from raghub_core.domain.rag.citations import resolve_trusted_citations
from raghub_core.domain.retrieval.hybrid import build_context_bundle, fuse_rrf
from raghub_core.domain.retrieval.models import RetrievedChunk


def test_text_to_trusted_context_without_runtime() -> None:
    chunks = chunk_sections(parse_document(b"# Guide\n\nUse RagHub.", "guide.md"), uuid4())
    hits = [
        RetrievedChunk(
            uuid4(),
            uuid4(),
            chunk.chunk_id,
            chunk.content,
            chunk.source_name,
            None,
            chunk.heading,
            1.0,
        )
        for chunk in chunks
    ]
    context = build_context_bundle(fuse_rrf([hits, hits], limit=5))
    assert "Use RagHub." in context.text
    assert resolve_trusted_citations(context.hits)[0].chunk_id == chunks[0].chunk_id
    assert estimate_chat_usage([ChatMessage("user", "question")], "answer").total_tokens > 0


def test_pdf_dispatch_uses_injected_decoder() -> None:
    section = ParsedSection("decoded", "guide.pdf", 0, page_number=1)
    assert parse_document(b"%PDF-", "guide.pdf", pdf_parser=lambda *_: [section]) == [section]
    with pytest.raises(ValueError, match="adapter"):
        parse_document(b"%PDF-", "guide.pdf")
