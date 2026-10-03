from uuid import uuid4

import pytest

from app.core_domain.ingestion.chunker import chunk_sections
from app.core_domain.ingestion.parser import ParsedSection, parse_document
from app.core_domain.providers.contracts import ChatMessage
from app.core_domain.providers.usage import estimate_chat_usage
from app.core_domain.rag.citations import resolve_citations
from app.core_domain.retrieval.hybrid import build_context_bundle, fuse_rrf


def test_text_to_trusted_context_without_runtime() -> None:
    chunks = chunk_sections(parse_document(b"# Guide\n\nUse RagHub.", "guide.md"), uuid4())
    hits = [
        {
            "document_id": str(uuid4()),
            "document_version_id": str(uuid4()),
            "chunk_id": str(chunk.chunk_id),
            "source_name": chunk.source_name,
            "content": chunk.content,
            "heading": chunk.heading,
            "page_number": None,
            "score": 1.0,
        }
        for chunk in chunks
    ]
    context = build_context_bundle(fuse_rrf([hits, hits], limit=5))
    assert "Use RagHub." in context.text
    assert resolve_citations(context.hits)[0]["chunk_id"] == str(chunks[0].chunk_id)
    assert estimate_chat_usage([ChatMessage("user", "question")], "answer").total_tokens > 0


def test_pdf_dispatch_uses_injected_decoder() -> None:
    section = ParsedSection("decoded", "guide.pdf", 0, page_number=1)
    assert parse_document(b"%PDF-", "guide.pdf", pdf_parser=lambda *_: [section]) == [section]
    with pytest.raises(ValueError, match="adapter"):
        parse_document(b"%PDF-", "guide.pdf")
