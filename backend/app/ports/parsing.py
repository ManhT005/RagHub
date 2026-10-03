from typing import Protocol

from app.core_domain.ingestion.parser import ParsedSection


class DocumentParserPort(Protocol):
    def parse(self, content: bytes, source_name: str) -> list[ParsedSection]: ...
