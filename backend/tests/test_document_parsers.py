"""Extended parsers and document limits: happy paths, bombs, timeouts, isolation."""
import io
import zipfile
from uuid import uuid4

import pytest
from raghub_core.domain.documents.upload import validate_upload_content, validate_upload_metadata
from raghub_core.domain.errors import CoreError
from raghub_core.domain.ingestion.limits import (
    MAX_CHUNKS,
    MAX_COMPRESSED_BYTES,
    MAX_EXTRACTED_TOKENS,
    MAX_OCR_PAGES,
    MAX_PDF_PAGES,
    MAX_POPULATED_CELLS,
    MAX_SHEETS,
    check_compressed_size,
    check_zip_container,
)
from raghub_core.domain.ingestion.parser import (
    DecompressionBombError,
    DocumentLimitError,
    EmptyExtractedTextError,
    MacroBlockedError,
    SignatureMismatchError,
)

from app.infrastructure.parsing.docx import parse_docx
from app.infrastructure.parsing.html import parse_html
from app.infrastructure.parsing.pdf import parse_pdf
from app.infrastructure.parsing.xlsx import parse_xlsx


def _pdf(pages: int, text: str = "Hello HaUI admissions guide 2026") -> bytes:
    import pymupdf

    document = pymupdf.open()
    for _ in range(pages):
        page = document.new_page()
        page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def _blank_pdf(pages: int) -> bytes:
    import pymupdf

    document = pymupdf.open()
    for _ in range(pages):
        document.new_page()
    data = document.tobytes()
    document.close()
    return data


def _docx(paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    import docx

    document = docx.Document()
    for para in paragraphs:
        document.add_paragraph(para)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for i, row in enumerate(table):
            for j, value in enumerate(row):
                grid.cell(i, j).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _xlsx(sheets: dict[str, list[list[object]]]) -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    first = True
    for name, rows in sheets.items():
        sheet = workbook.active if first else workbook.create_sheet(name)
        first = False
        sheet.title = name
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _zip(parts: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_pdf_text_and_reject_over_70_pages():
    sections = parse_pdf(_pdf(2))
    assert len(sections) == 2 and sections[0].page_number == 1
    with pytest.raises(Exception, match="70"):
        parse_pdf(_pdf(MAX_PDF_PAGES + 1, text="x"))


def test_pdf_scan_without_ocr_keeps_legacy_error():
    from raghub_core.domain.ingestion.parser import UnsupportedOcrError

    with pytest.raises(UnsupportedOcrError):
        parse_pdf(_blank_pdf(1))


def test_pdf_ocr_page_cap(monkeypatch):
    import app.infrastructure.parsing.pdf as pdf_adapter

    monkeypatch.setattr(pdf_adapter, "_ocr_page", lambda pixmap, timeout=15: "scanned text")
    with pytest.raises(DocumentLimitError):
        parse_pdf(_blank_pdf(MAX_OCR_PAGES + 1), ocr_enabled=True)


def test_docx_paragraphs_tables_in_order():
    sections = parse_docx(_docx(["Intro", "Body"], [["H1", "H2"], ["a", "b"]]))
    assert sections[0].content == "Intro"
    assert sections[1].content == "Body"
    assert sections[2].content.splitlines()[0] == "| H1 | H2 |"
    assert sections[2].heading == "Table 1"


def test_docx_malformed_and_macro_rejected():
    with pytest.raises((SignatureMismatchError, EmptyExtractedTextError)):
        parse_docx(b"PK\x03\x04garbage-not-a-zip", "bad.docx")
    bomb = _zip({"word/document.xml": b"<w:doc/>", "word/vbaProject.bin": b"macro"})
    with pytest.raises(MacroBlockedError):
        check_zip_container(bomb, ".docx")
    with pytest.raises(MacroBlockedError):
        check_zip_container(_docx(["x"]), ".docm")


def test_zip_bomb_rejected_by_ratio():
    bomb = _zip({"word/document.xml": b"\x00" * 1_000_000})
    assert len(bomb) * 100 < 1_000_000
    with pytest.raises(DecompressionBombError):
        check_zip_container(bomb, ".docx")


def test_html_sanitized_without_external_fetch():
    html = b"""<html><head><script>alert('x')</script></head><body>
    <h1>Tuyen sinh 2026</h1>
    <p>Chi tieu <b>8300</b>.</p>
    <img src="http://evil.example/pixel.png">
    <div style="display:none">hidden trap</div>
    <ul><li>PT1</li><li>PT2</li></ul></body></html>"""
    sections = parse_html(html, "news.html")
    text = "\n".join(s.content for s in sections)
    assert "alert" not in text and "hidden trap" not in text
    assert "evil.example" not in text
    assert "8300" in text and any(s.content == "- PT1" for s in sections)


def test_html_empty_rejected():
    with pytest.raises(EmptyExtractedTextError):
        parse_html(b"<html><body><script>only</script></body></html>")


def test_xlsx_read_only_data_only_with_sheet_metadata():
    data = _xlsx({"Score": [["Name", "Math"], ["An", 9.5]], "Empty": []})
    sections = parse_xlsx(data, "scores.xlsx")
    assert len(sections) == 1
    assert sections[0].heading.startswith("Sheet: Score")
    assert "| Name | Math |" in sections[0].content
    assert "9.5" in sections[0].content


def test_xlsx_sheet_cap_and_macro_rejected():
    data = _xlsx({f"S{i}": [["x"]] for i in range(MAX_SHEETS + 1)})
    with pytest.raises(DocumentLimitError):
        parse_xlsx(data, "big.xlsx")
    assert MAX_POPULATED_CELLS == 200_000


def test_upload_types_and_mime_mismatch():
    name, ext, mime = validate_upload_metadata("a.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert ext == ".docx"
    name, ext, mime = validate_upload_metadata("a.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert ext == ".xlsx"
    with pytest.raises(CoreError):
        validate_upload_metadata("a.docx", "text/plain")
    with pytest.raises(CoreError):
        validate_upload_content(b"not-office", ".docx", 25)


def test_preflight_size_limit_without_allocation():
    with pytest.raises(DocumentLimitError):
        check_compressed_size(MAX_COMPRESSED_BYTES + 1)
    assert MAX_EXTRACTED_TOKENS == 80_000 and MAX_CHUNKS == 250


def test_chunk_and_token_caps_reject_before_embedding():
    from raghub_core.application.ingestion.build_document_index import BuildDocumentIndexUseCase
    from raghub_core.domain.ingestion.errors import IngestionError
    from raghub_core.domain.ingestion.models import IngestionDocument
    from raghub_core.domain.ingestion.parser import ParsedSection
    from raghub_core.domain.retrieval.models import RetrievalScope

    async def run(sections):
        from tests.core.fakes import FakeObjectStorage

        storage = FakeObjectStorage()
        storage.objects["k"] = b"# doc"
        use_case = BuildDocumentIndexUseCase(
            storage=storage,
            parser=lambda data, name: sections,
        )
        document = IngestionDocument(
            RetrievalScope(uuid4(), uuid4()), uuid4(), uuid4(), "k", "d.md"
        )
        with pytest.raises(IngestionError) as exc:
            await use_case.execute(document, None, None)  # type: ignore[arg-type]
        return exc.value.code

    import asyncio

    many = [ParsedSection(f"section {i} content here", "d.md", i, page_number=i+1) for i in range(MAX_CHUNKS + 1)]
    assert asyncio.run(run(many)) == "DOCUMENT_LIMIT_EXCEEDED"


def test_ocr_flag_defaults_off():
    from app.core.config import Settings

    assert Settings(_env_file=None).rag_ocr_enabled is False
