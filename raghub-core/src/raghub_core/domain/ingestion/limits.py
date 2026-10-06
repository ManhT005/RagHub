"""Shared preflight limits for document parsing (safe for 50-70 page docs).

All checks run before parsing/embedding so oversized or hostile files fail
with a clear code and never activate a half-built index.
"""

from __future__ import annotations

import io
import zipfile

from raghub_core.domain.ingestion.parser import (
    DecompressionBombError,
    DocumentLimitError,
    MacroBlockedError,
    SignatureMismatchError,
)

MAX_COMPRESSED_BYTES = 25 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_PDF_PAGES = 70
MAX_OCR_PAGES = 50
MAX_EXTRACTED_TOKENS = 80_000
MAX_CHUNKS = 250
MAX_SHEETS = 50
MAX_POPULATED_CELLS = 200_000
MAX_ZIP_RATIO = 100
OCR_PAGE_TIMEOUT_SECONDS = 15
OCR_DOCUMENT_TIMEOUT_SECONDS = 600
OCR_USEFUL_CHARS_THRESHOLD = 20

ZIP_CONTAINER_EXTENSIONS = frozenset({".docx", ".xlsx"})
MACRO_EXTENSIONS = frozenset({".docm", ".xlsm"})
MACRO_PARTS = ("word/vbaProject.bin", "xl/vbaProject.bin")

SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
}


def check_compressed_size(size_bytes: int) -> None:
    if size_bytes > MAX_COMPRESSED_BYTES:
        raise DocumentLimitError(f"File exceeds {MAX_COMPRESSED_BYTES} compressed bytes.")


def check_zip_container(content: bytes, extension: str) -> int:
    """Validate an Office container: ratio cap, macro scan, sheet/cell budget base."""
    if extension in MACRO_EXTENSIONS:
        raise MacroBlockedError("Macro-enabled documents are rejected.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise SignatureMismatchError("Office file is not a valid ZIP container.") from exc
    with archive:
        names = archive.namelist()
        for part in MACRO_PARTS:
            if part in names:
                raise MacroBlockedError("Macro-enabled documents are rejected.")
        total = sum(info.file_size for info in archive.infolist())
        if len(content) > 0 and total / max(1, len(content)) > MAX_ZIP_RATIO:
            raise DecompressionBombError("Archive compression ratio exceeds 100:1.")
        if total > MAX_DECOMPRESSED_BYTES:
            raise DocumentLimitError("Decompressed content exceeds 100 MB.")
        return total


def check_signature(content: bytes, extension: str) -> None:
    prefixes = SIGNATURES.get(extension)
    if prefixes and not content.startswith(prefixes):
        raise SignatureMismatchError("File signature does not match its extension.")
    if extension in MACRO_EXTENSIONS:
        raise MacroBlockedError("Macro-enabled documents are rejected.")
