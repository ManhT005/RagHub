import uuid

import pymupdf
import pytest

from app.modules.ingestion.chunker import chunk_sections
from app.modules.ingestion.parser import (
    InvalidPdfError,
    ParsedSection,
    TextDecodeError,
    UnsupportedOcrError,
    parse_document,
    parse_pdf,
)
from app.modules.ingestion.tokenizer import ENCODING


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
    chunks = chunk_sections(pages, uuid.uuid4())
    assert [page.page_number for page in pages] == [1, 2]
    assert [chunk.page_number for chunk in chunks] == [1, 2]
    assert [chunk.content for chunk in chunks] == ["First page content", "Second page content"]


def test_markdown_and_txt_preserve_metadata() -> None:
    sections = parse_document(b"# Authentication\n\nLog in.\n\n## Refresh\n\nRenew token.", "a.md")
    assert [section.heading for section in sections] == ["Authentication", "Refresh"]
    assert [chunk.heading for chunk in chunk_sections(sections, uuid.uuid4())] == [
        "Authentication",
        "Refresh",
    ]
    text = parse_document("Đoạn một\n\nĐoạn hai".encode(), "a.txt")
    assert len(text) == 1
    assert text[0].content == "Đoạn một\n\nĐoạn hai"
    assert all(section.page_number is None and section.heading is None for section in text)
    with pytest.raises(TextDecodeError):
        parse_document(b"\xff", "a.txt")


def test_chunk_limits_overlap_and_stable_ids() -> None:
    version_id = uuid.uuid4()
    text = " ".join(f"word{i}" for i in range(900))
    section = ParsedSection(text, "a.txt", 0)
    first = chunk_sections([section], version_id)
    second = chunk_sections([section], version_id)
    assert len(first) > 1
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert all(chunk.token_count <= 450 for chunk in first)
    assert all(chunk.token_count >= 80 for chunk in first)
    assert first[0].chunk_id != chunk_sections([section], uuid.uuid4())[0].chunk_id
    a = ENCODING.encode(first[0].content)
    b = ENCODING.encode(first[1].content)
    assert ENCODING.decode(a[-80:]).strip() == ENCODING.decode(b[:80]).strip()


def test_invalid_and_image_only_pdf() -> None:
    with pytest.raises(InvalidPdfError):
        parse_pdf(b"not a pdf")
    with pytest.raises(UnsupportedOcrError):
        parse_pdf(_pdf_with_text(""))


def test_unicode_survives_token_boundaries() -> None:
    text = " ".join(["Thông tin tiếng Việt"] * 500)
    chunks = chunk_sections([ParsedSection(text, "vietnamese.txt", 0)], uuid.uuid4())
    assert len(chunks) > 1
    assert all("�" not in chunk.content and chunk.token_count <= 450 for chunk in chunks)


@pytest.mark.parametrize("paragraph_count", [8, 25, 100])
def test_short_txt_paragraphs_merge_before_chunking(paragraph_count: int) -> None:
    paragraphs = [f"Paragraph {index}: " + "information " * 15 for index in range(paragraph_count)]
    sections = parse_document("\n\n".join(paragraphs).encode(), "paragraphs.txt")
    chunks = chunk_sections(sections, uuid.uuid4())
    assert len(chunks) < paragraph_count
    assert all(80 <= chunk.token_count <= 450 for chunk in chunks)
    for index in range(paragraph_count):
        assert any(f"Paragraph {index}:" in chunk.content for chunk in chunks)


def test_short_document_is_kept_and_global_indexes_preserve_citations() -> None:
    sections = parse_pdf(_pdf_with_text("Page one", "Page two"))
    chunks = chunk_sections(sections, uuid.uuid4())
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert [chunk.page_number for chunk in chunks] == [1, 2]
    assert [chunk.content for chunk in chunks] == ["Page one", "Page two"]
    sections = parse_document(b"# First\n\nShort.\n\n# Second\n\nAlso short.", "headings.md")
    chunks = chunk_sections(sections, uuid.uuid4())
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert [chunk.heading for chunk in chunks] == ["First", "Second"]


@pytest.mark.parametrize(
    "opening,inner,closing",
    [
        ("```md", "~~~", "```"),
        ("~~~~", "~~~", "~~~~"),
        ("````", "```", "````"),
    ],
)
def test_markdown_fences_do_not_create_headings(opening: str, inner: str, closing: str) -> None:
    text = f"# Real\n\n{opening}\n# Code\n{inner}\n# Still code\n{closing}\n\n# Next\n\nBody"
    sections = parse_document(text.encode(), "code.md")
    assert [section.heading for section in sections] == ["Real", "Next"]
    assert "# Code" in sections[0].content and "# Still code" in sections[0].content
