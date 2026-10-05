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
            if _useful_chars(text) < OCR_USEFUL_CHARS_THRESHOLD and not tables:
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
                    pixmap = page.get_pixmap(dpi=200)
                    text = _ocr_page(pixmap.tobytes("png"))
            body = text
            if tables:
                body = (body + "\n\n" + "\n\n".join(tables)).strip()
            if body:
                sections.append(ParsedSection(body, source_name, len(sections), index + 1))
        return sections
    finally:
        document.close()
