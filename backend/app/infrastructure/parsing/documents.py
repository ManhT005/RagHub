from app.core_domain.ingestion.parser import ParsedSection, parse_document
from app.infrastructure.parsing.pdf import parse_pdf


class DocumentParser:
    def parse(self, content: bytes, source_name: str) -> list[ParsedSection]:
        return parse_document(content, source_name, pdf_parser=parse_pdf)
