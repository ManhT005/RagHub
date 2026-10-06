"""PDF adapter: text-first, PyMuPDF tables, heuristic Tesseract OCR.

OCR runs at most one page at a time per worker (process-local slot) with a
15s/page and 10-minute/document budget. OCR is off unless RAG_OCR_ENABLED;
a page that needs OCR while disabled fails with a clear code instead of a
half-built index.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time

import pymupdf
from raghub_core.domain.ingestion.limits import (
    MAX_OCR_PAGES,
    MAX_PDF_PAGES,
    OCR_DOCUMENT_TIMEOUT_SECONDS,
    OCR_PAGE_TIMEOUT_SECONDS,
    OCR_USEFUL_CHARS_THRESHOLD,
    check_compressed_size,
    check_signature,
)
from raghub_core.domain.ingestion.parser import (
    DocumentLimitError,
    InvalidPdfError,
    OcrRequiredError,
    OcrTimeoutError,
    ParsedBlock,
    ParsedSection,
    UnsupportedOcrError,
)

_OCR_SLOT = threading.Semaphore(1)
_OCR_LANGUAGES = "vie+eng"


def _useful_chars(text: str) -> int:
    return sum(1 for ch in text if ch.isalnum())


def _ocr_page(pixmap: bytes, *, timeout: int = OCR_PAGE_TIMEOUT_SECONDS) -> str:
    tesseract = shutil.which("tesseract")
    if tesseract is None:
        raise OcrRequiredError("OCR requested but the Tesseract binary is missing.")
    try:
        completed = subprocess.run(
            [tesseract, "stdin", "stdout", "-l", _OCR_LANGUAGES],
            input=pixmap,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise OcrTimeoutError("OCR exceeded the 15s page budget.") from exc
    if completed.returncode != 0:
        raise OcrRequiredError("Tesseract failed on this page.")
    return completed.stdout.decode("utf-8", errors="replace").strip()


def _table_markdown(page: pymupdf.Page) -> list[str]:
    blocks: list[str] = []
    try:
        tables = page.find_tables()
    except Exception:
        return blocks
    for table in tables:
        rows = [[(cell or "").strip() for cell in row] for row in table.extract()]
        rows = [row for row in rows if any(row)]
        if not rows:
            continue
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
        lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
        blocks.append("\n".join(lines))
    return blocks


def parse_pdf(
    content: bytes,
    source_name: str = "document.pdf",
    *,
    ocr_enabled: bool = False,
    ocr_deadline: float | None = None,
    telemetry=None,
) -> list[ParsedSection]:
    check_compressed_size(len(content))
    check_signature(content, ".pdf")
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise InvalidPdfError("The PDF cannot be opened or read.") from exc
    try:
        if document.page_count > MAX_PDF_PAGES:
            raise InvalidPdfError(f"PDF exceeds {MAX_PDF_PAGES} pages.")
        deadline = ocr_deadline or (time.monotonic() + OCR_DOCUMENT_TIMEOUT_SECONDS)
        sections: list[ParsedSection] = []
        ocr_pages = 0
        for index, page in enumerate(document):
            text = page.get_text("text").strip()
            tables = _table_markdown(page)
            kind = "paragraph"
            text_blocks = page.get_text("blocks")
            image_area = sum(
                pymupdf.Rect(info["bbox"]).get_area() for info in page.get_image_info()
            )
            image_ratio = image_area / max(1, page.rect.get_area())
            useful = _useful_chars(text)
            needs_ocr = not tables and (
                useful < OCR_USEFUL_CHARS_THRESHOLD
                or (image_ratio > 0.8 and useful < 80 and len(text_blocks) < 3)
            )
            if needs_ocr:
                if not ocr_enabled:
                    raise UnsupportedOcrError(
                        "The PDF needs OCR, which is disabled (RAG_OCR_ENABLED)."
                    )
                ocr_pages += 1
                if ocr_pages > MAX_OCR_PAGES:
                    raise DocumentLimitError(f"PDF needs more than {MAX_OCR_PAGES} OCR pages.")
                if time.monotonic() > deadline:
                    raise OcrTimeoutError("OCR exceeded the document time budget.")
                with _OCR_SLOT:
                    mark = time.perf_counter()
                    pixmap = page.get_pixmap(dpi=200)
                    text = _ocr_page(pixmap.tobytes("png"))
                    kind = "ocr_text"
                    if telemetry is not None:
                        telemetry.timing("ocr", (time.perf_counter() - mark) * 1000, {})
                        telemetry.counter("ocr_pages", {})
            if text:
                sections.append(ParsedBlock(text, source_name, len(sections), index + 1, type=kind))
            for table in tables:
                sections.append(
                    ParsedBlock(table, source_name, len(sections), index + 1, type="table")
                )
        return sections
    finally:
        document.close()
