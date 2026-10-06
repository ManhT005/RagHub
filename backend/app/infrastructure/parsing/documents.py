"""Parser registry: preflight first, then one isolated adapter per format.

Adapter isolation: a malformed file in one format raises a file-scoped
error and never affects other formats.
"""

from raghub_core.domain.ingestion.limits import check_compressed_size
from raghub_core.domain.ingestion.parser import ParsedSection, parse_document

from app.core.config import get_settings
from app.infrastructure.parsing.docx import parse_docx
from app.infrastructure.parsing.html import parse_html
from app.infrastructure.parsing.pdf import parse_pdf
from app.infrastructure.parsing.xlsx import parse_xlsx


class DocumentParser:
    def parse(self, content: bytes, source_name: str) -> list[ParsedSection]:
        check_compressed_size(len(content))
        settings = get_settings()
        return parse_document(
            content,
            source_name,
            pdf_parser=lambda data, name: parse_pdf(
                data, name, ocr_enabled=settings.rag_ocr_enabled
            ),
            docx_parser=parse_docx,
            html_parser=parse_html,
            xlsx_parser=parse_xlsx,
        )
