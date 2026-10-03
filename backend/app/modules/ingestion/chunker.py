"""Compatibility imports; new callers should use app.core_domain.ingestion.chunker."""

from app.core_domain.ingestion.chunker import (
    TextChunk as TextChunk,
)
from app.core_domain.ingestion.chunker import (
    chunk_pages as chunk_pages,
)
from app.core_domain.ingestion.chunker import (
    chunk_sections as chunk_sections,
)
