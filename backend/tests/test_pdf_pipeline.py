import uuid

import pymupdf

from app.modules.ingestion.chunker import chunk_pages
from app.modules.ingestion.parser import ParsedPage, UnsupportedOcrError, parse_pdf


def _pdf_with_text(*page_texts: str) -> bytes:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def test_pdf_pages_keep_citation_boundaries() -> None:
    pages = parse_pdf(_pdf_with_text("First page content", "Second page content"))
    chunks = chunk_pages(pages, uuid.UUID("70e09413-0430-4439-b585-a9f48f06c21b"))

    assert [page.page_number for page in pages] == [1, 2]
    assert [chunk.page_number for chunk in chunks] == [1, 2]
    assert chunks[0].content == "First page content"
    assert chunks[1].content == "Second page content"


def test_chunk_ids_are_stable() -> None:
    version_id = uuid.UUID("70e09413-0430-4439-b585-a9f48f06c21b")
    pages = [ParsedPage(page_number=1, content="one two three four five")]

    first = chunk_pages(pages, version_id, target_words=3, overlap_words=1)
    second = chunk_pages(pages, version_id, target_words=3, overlap_words=1)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert [chunk.content for chunk in first] == ["one two three", "three four five"]


def test_image_only_pdf_is_rejected() -> None:
    document = pymupdf.open()
    document.new_page()
    content = document.tobytes()
    document.close()

    try:
        parse_pdf(content)
    except UnsupportedOcrError as exc:
        assert "OCR" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected an image-only PDF to be rejected")
