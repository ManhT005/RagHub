from typing import Protocol

from raghub_core.domain.ingestion.parser import ParsedSection


class DocumentParserPort(Protocol):
    def parse(self, content: bytes, source_name: str) -> list[ParsedSection]: ...
