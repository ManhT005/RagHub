"""Compatibility imports; new callers should use raghub_core.domain.ingestion.parser."""

from raghub_core.domain.ingestion.parser import (
    DecompressionBombError as DecompressionBombError,
)
from raghub_core.domain.ingestion.parser import (
    DocumentLimitError as DocumentLimitError,
)
from raghub_core.domain.ingestion.parser import (
    EmptyExtractedTextError as EmptyExtractedTextError,
)
from raghub_core.domain.ingestion.parser import (
    InvalidPdfError as InvalidPdfError,
)
from raghub_core.domain.ingestion.parser import (
    MacroBlockedError as MacroBlockedError,
)
from raghub_core.domain.ingestion.parser import (
    OcrRequiredError as OcrRequiredError,
)
from raghub_core.domain.ingestion.parser import (
    OcrTimeoutError as OcrTimeoutError,
)
from raghub_core.domain.ingestion.parser import (
    ParsedSection as ParsedSection,
)
from raghub_core.domain.ingestion.parser import (
    SignatureMismatchError as SignatureMismatchError,
)
from raghub_core.domain.ingestion.parser import (
    TextDecodeError as TextDecodeError,
)
from raghub_core.domain.ingestion.parser import (
    UnsupportedFileTypeError as UnsupportedFileTypeError,
)
from raghub_core.domain.ingestion.parser import (
    UnsupportedOcrError as UnsupportedOcrError,
)
from raghub_core.domain.ingestion.parser import (
    parse_document as _parse_document,
)
from raghub_core.domain.ingestion.parser import (
    parse_markdown as parse_markdown,
)
from raghub_core.domain.ingestion.parser import (
    parse_txt as parse_txt,
)

from app.infrastructure.parsing.pdf import parse_pdf as parse_pdf


def parse_document(content: bytes, source_name: str) -> list[ParsedSection]:
    """Compatibility composition for the existing PDF/TXT/Markdown pipeline."""
    return _parse_document(content, source_name, pdf_parser=parse_pdf)
