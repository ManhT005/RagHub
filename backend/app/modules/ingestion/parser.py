"""Compatibility imports; new callers should use app.core_domain.ingestion.parser."""

from app.core_domain.ingestion.parser import (
    EmptyExtractedTextError as EmptyExtractedTextError,
)
from app.core_domain.ingestion.parser import (
    InvalidPdfError as InvalidPdfError,
)
from app.core_domain.ingestion.parser import (
    ParsedSection as ParsedSection,
)
from app.core_domain.ingestion.parser import (
    TextDecodeError as TextDecodeError,
)
from app.core_domain.ingestion.parser import (
    UnsupportedFileTypeError as UnsupportedFileTypeError,
)
from app.core_domain.ingestion.parser import (
    UnsupportedOcrError as UnsupportedOcrError,
)
from app.core_domain.ingestion.parser import (
    parse_document as _parse_document,
)
from app.core_domain.ingestion.parser import (
    parse_markdown as parse_markdown,
)
from app.core_domain.ingestion.parser import (
    parse_txt as parse_txt,
)
from app.infrastructure.parsing.pdf import parse_pdf as parse_pdf


def parse_document(content: bytes, source_name: str) -> list[ParsedSection]:
    """Compatibility composition for the existing PDF/TXT/Markdown pipeline."""
    return _parse_document(content, source_name, pdf_parser=parse_pdf)
