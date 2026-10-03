from app.infrastructure.parsing.pdf import parse_pdf
from raghub_core.domain.ingestion.parser import ParsedSection, parse_document


class DocumentParser:
    def parse(self, content: bytes, source_name: str) -> list[ParsedSection]:
        return parse_document(content, source_name, pdf_parser=parse_pdf)
