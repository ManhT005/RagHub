import io
import shutil
from uuid import uuid4

import docx
import openpyxl
import pymupdf
import pytest
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from raghub_core.domain.ingestion.markdown_v2 import chunk_markdown_blocks
from raghub_core.domain.ingestion.parser import EmptyExtractedTextError, TextDecodeError
from raghub_core.domain.ingestion.tokenizer import ENCODING

from app.infrastructure.parsing.documents import DocumentParser
from app.infrastructure.parsing.docx import parse_docx
from app.infrastructure.parsing.html import parse_html
from app.infrastructure.parsing.pdf import parse_pdf
from app.infrastructure.parsing.xlsx import parse_xlsx


def workbook(rows):
    book = openpyxl.Workbook()
    for row in rows:
        book.active.append(row)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def test_html_v2_prefers_main_and_removes_navigation_without_changing_legacy():
    html = (
        b"<nav>Menu trap</nav><p>Outside</p><main><header><h1>Guide</h1></header>"
        b"<h3>Deep</h3><h2>Setup</h2><p>Useful fact</p><aside>Sidebar trap</aside>"
        b"<footer>Footer trap</footer></main>"
    )
    old = parse_html(html)
    new = parse_html(html, structured=True)
    assert "Menu trap" in " ".join(b.content for b in old)
    text = " ".join(b.content for b in new)
    assert "trap" not in text and "Outside" not in text and "Useful fact" in text
    assert new[-1].heading_path == ("Guide", "Setup")


def test_html_v2_keeps_code_whitespace_and_no_main_fallback():
    blocks = parse_html(
        b"<nav>Menu</nav><h1>Guide</h1><pre><code>    x = 1\n\n    y = 2</code></pre>",
        structured=True,
    )
    assert blocks[-1].content == "    x = 1\n\n    y = 2"
    chunks = chunk_markdown_blocks(blocks, uuid4(), pipeline="document-v2")
    assert chunks[0].content == blocks[-1].content
    assert "Menu" not in " ".join(b.content for b in blocks)


def test_html_v2_keeps_numbered_list_start_and_warns_on_complex_spans():
    blocks = parse_html(
        (
            b'<main><ol start="4"><li>First</li><li>Second</li></ol><table>'
            b'<tr><th colspan="2">Merged</th></tr><tr><td>a</td><td>b</td></tr></table></main>'
        ),
        structured=True,
    )
    assert [b.content for b in blocks if b.type == "list"] == ["4. First", "5. Second"]
    assert next(b for b in blocks if b.type == "table").metadata["quality_warnings"] == [
        "TABLE_SPANS_REQUIRE_REVIEW"
    ]


def test_html_v2_deduplicates_only_paragraphs_not_list_items():
    blocks = parse_html(
        (b"<main><p>Repeated fact</p><p>Repeated fact</p><ul>"
         b"<li>Same item</li><li>Same item</li></ul></main>"),
        structured=True,
    )
    assert len([b for b in blocks if b.type == "paragraph"]) == 1
    assert len([b for b in blocks if b.type == "list"]) == 2
    assert blocks[0].metadata["duplicate_paragraphs_removed"] == 1


def test_docx_v2_keeps_numbered_lists_and_table_order():
    document = docx.Document()
    document.add_heading("Guide", 1)
    document.add_paragraph("First", style="List Number")
    document.add_paragraph("Second", style="List Number")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Key"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "alpha"
    table.cell(1, 1).text = "42"
    document.add_paragraph("After table")
    output = io.BytesIO()
    document.save(output)
    blocks = parse_docx(output.getvalue(), structured=True)
    assert [b.type for b in blocks] == ["heading", "list", "list", "table", "paragraph"]
    assert blocks[1].content == "1. First" and blocks[2].content == "2. Second"
    assert "alpha" in blocks[3].content and blocks[-1].content == "After table"


def test_docx_v2_honors_outline_levels_and_skipped_heading_levels():
    document = docx.Document()
    document.add_heading("Guide", 1)
    document.add_heading("Deep", 3)
    paragraph = document.add_paragraph("Next")
    outline = OxmlElement("w:outlineLvl")
    outline.set(qn("w:val"), "1")
    paragraph._p.get_or_add_pPr().append(outline)
    document.add_paragraph("Body")
    output = io.BytesIO()
    document.save(output)
    blocks = parse_docx(output.getvalue(), structured=True)
    assert blocks[-1].heading_path == ("Guide", "Next")


def test_docx_v2_merged_cells_do_not_duplicate_text_or_destroy_literal_pipes():
    document = docx.Document()
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "A"
    table.cell(0, 1).text = "B"
    table.cell(1, 0).merge(table.cell(1, 1)).text = "literal | pipe"
    output = io.BytesIO()
    document.save(output)
    block = parse_docx(output.getvalue(), structured=True)[0]
    assert block.content.count("literal") == 1 and "literal \\| pipe" in block.content


def test_xlsx_v2_splits_blank_separated_tables_and_preserves_row_coordinates():
    data = workbook([["Name", "Score"], ["An", 9], [], ["City", "Count"], ["HN", 20]])
    blocks = parse_xlsx(data, structured=True)
    assert len(blocks) == 2
    assert blocks[0].metadata["row_numbers"] == [2]
    assert blocks[1].metadata["header_row"] == 4
    assert "| City | Count |" in blocks[1].content
    chunks = chunk_markdown_blocks(blocks, uuid4(), pipeline="document-v2")
    assert chunks[1].metadata["row_start"] == 5
    assert all(c.metadata["sheet"] == "Sheet" for c in chunks)


def test_xlsx_v2_warns_about_missing_formula_cache_and_does_not_execute_formula():
    blocks = parse_xlsx(workbook([["Name", "Value"], ["Calculation", "=1+2"]]), structured=True)
    assert blocks[0].metadata["quality_warnings"] == ["FORMULA_WITHOUT_CACHED_VALUE"]
    assert blocks[0].metadata["formula_cells_without_cache"] == ["B2"]
    assert "=1+2" not in blocks[0].content


def test_xlsx_v2_preserves_numeric_first_row_and_empty_leading_columns():
    blocks = parse_xlsx(workbook([[None, 1, 2], [None, 3, 4]]), structured=True)
    assert blocks[0].metadata["header_inferred"]
    assert "|  | 1 | 2 |" in blocks[0].content
    assert blocks[0].metadata["row_numbers"] == [1, 2]


def test_xlsx_v2_recognizes_title_and_caps_large_sparse_grids():
    data = workbook([["Results"], ["Name", "Value"], ["An", 1]])
    blocks = parse_xlsx(data, structured=True)
    assert blocks[0].type == "heading" and blocks[1].metadata["header_row"] == 2
    book = openpyxl.Workbook()
    book.active.cell(1_000_000, 100, "x")
    output = io.BytesIO()
    book.save(output)
    from raghub_core.domain.ingestion.parser import DocumentLimitError

    with pytest.raises(DocumentLimitError, match="sparse"):
        parse_xlsx(output.getvalue(), structured=True)


def test_text_v2_utf8_bom_paragraphs_lists_and_no_nul():
    parser = DocumentParser()
    blocks = parser.parse_v2(b"\xef\xbb\xbfIntro\r\n\r\n1. First\r\n2. Second", "guide.txt")
    assert [b.type for b in blocks] == ["paragraph", "list"]
    assert blocks[1].metadata["line_start"] == 3
    chunks = chunk_markdown_blocks(blocks, uuid4(), pipeline="document-v2")
    assert all(len(ENCODING.encode(c.embedding_content)) <= 450 for c in chunks)
    with pytest.raises(TextDecodeError):
        parser.parse_v2(b"hello\x00world", "bad.txt")
    with pytest.raises(TextDecodeError):
        parser.parse_v2(b"\xff", "bad.txt")


def test_pdf_v2_removes_repeated_margins_and_keeps_page_metadata():
    document = pymupdf.open()
    for i in range(3):
        page = document.new_page()
        page.insert_text((40, 25), "Repeated portal header")
        page.insert_text((40, 200), f"Important body information on page {i + 1}.")
        page.insert_text((40, 820), f"Page {i + 1}")
    blocks = parse_pdf(document.tobytes(), structured=True)
    assert all("Repeated portal header" not in b.content for b in blocks)
    assert [b.page_number for b in blocks] == [1, 2, 3]
    chunks = chunk_markdown_blocks(blocks, uuid4(), pipeline="document-v2")
    assert [c.page_number for c in chunks] == [1, 2, 3]
    assert "Page: 1" in chunks[0].embedding_content


def test_pdf_v2_reads_two_columns_in_column_order():
    document = pymupdf.open()
    page = document.new_page()
    for x, label in [(40, "LEFT"), (350, "RIGHT")]:
        page.insert_text((x, 200), label + " FIRST")
        page.insert_text((x, 300), label + " SECOND")
    blocks = parse_pdf(document.tobytes(), structured=True)
    assert [b.content for b in blocks] == [
        "LEFT FIRST",
        "LEFT SECOND",
        "RIGHT FIRST",
        "RIGHT SECOND",
    ]
    assert blocks[0].metadata["reading_order"] == "two-column"


def test_pdf_v2_short_text_is_not_forced_to_ocr_and_empty_pages_are_skipped():
    document = pymupdf.open()
    document.new_page()
    page = document.new_page()
    page.insert_text((40, 200), "Title")
    blocks = parse_pdf(document.tobytes(), structured=True)
    assert len(blocks) == 1 and blocks[0].page_number == 2
    empty = pymupdf.open()
    empty.new_page()
    with pytest.raises(EmptyExtractedTextError):
        parse_pdf(empty.tobytes(), structured=True)


def test_pdf_v2_detected_table_cells_are_not_duplicated_as_paragraphs():
    document = pymupdf.open()
    page = document.new_page()
    for y in [150, 200, 250]:
        page.draw_line((40, y), (400, y))
    for x in [40, 200, 400]:
        page.draw_line((x, 150), (x, 250))
    for x, y, text in [
        (50, 180, "Field"),
        (210, 180, "Value"),
        (50, 230, "unique-record"),
        (210, 230, "42"),
    ]:
        page.insert_text((x, y), text)
    blocks = parse_pdf(document.tobytes(), structured=True)
    assert any(b.type == "table" for b in blocks)
    assert "\n".join(b.content for b in blocks).count("unique-record") == 1


def scan_pdf():
    source = pymupdf.open()
    page = source.new_page()
    page.insert_text((40, 200), "RAGHub document processing benchmark", fontsize=20)
    image = page.get_pixmap(dpi=150).tobytes("png")
    target = pymupdf.open()
    page = target.new_page()
    page.insert_image(page.rect, stream=image)
    return target.tobytes()


def test_pdf_v2_ocr_is_selective_bounded_and_warns_on_low_text(monkeypatch):
    import app.infrastructure.parsing.pdf as adapter

    calls = []

    def ocr(image, **options):
        calls.append(options)
        return "Recognized short text"

    monkeypatch.setattr(adapter, "_ocr_page", ocr)
    blocks = parse_pdf(scan_pdf(), structured=True, ocr_enabled=True)
    assert len(calls) == 1 and calls[0]["auto_rotate"] and calls[0]["timeout"] <= 15
    assert blocks[0].type == "ocr_text" and blocks[0].metadata["quality_warnings"] == [
        "OCR_LOW_TEXT"
    ]


def test_pdf_v2_enforces_ocr_deadline_and_page_limit(monkeypatch):
    import time

    from raghub_core.domain.ingestion.parser import DocumentLimitError, OcrTimeoutError

    import app.infrastructure.parsing.pdf as adapter

    with pytest.raises(OcrTimeoutError):
        parse_pdf(scan_pdf(), structured=True, ocr_enabled=True, ocr_deadline=time.monotonic() - 1)
    monkeypatch.setattr(adapter, "MAX_OCR_PAGES", 1)
    monkeypatch.setattr(adapter, "_ocr_page", lambda data, **kw: "Recognized text")
    source = pymupdf.open(stream=scan_pdf(), filetype="pdf")
    document = pymupdf.open()
    document.insert_pdf(source)
    document.insert_pdf(source)
    with pytest.raises(DocumentLimitError, match="OCR pages"):
        parse_pdf(document.tobytes(), structured=True, ocr_enabled=True)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="OCR binary required")
def test_pdf_v2_real_ocr_image_smoke():
    blocks = parse_pdf(scan_pdf(), structured=True, ocr_enabled=True)
    assert "processing" in " ".join(b.content.lower() for b in blocks)
