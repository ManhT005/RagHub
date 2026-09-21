import hashlib
import uuid
from dataclasses import dataclass

from app.modules.ingestion.parser import ParsedPage


@dataclass(frozen=True, slots=True)
class TextChunk:
    chunk_id: uuid.UUID
    page_number: int
    chunk_index: int
    content: str


def chunk_pages(
    pages: list[ParsedPage],
    document_version_id: uuid.UUID,
    *,
    target_words: int = 450,
    overlap_words: int = 80,
) -> list[TextChunk]:
    if target_words <= 0 or overlap_words < 0 or overlap_words >= target_words:
        raise ValueError("Chunk size must be positive and overlap smaller than the target.")

    chunks: list[TextChunk] = []
    step = target_words - overlap_words
    for page in pages:
        words = page.content.split()
        for chunk_index, start in enumerate(range(0, len(words), step)):
            chunk_words = words[start : start + target_words]
            if not chunk_words:
                continue
            text = " ".join(chunk_words)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chunk_id = uuid.uuid5(
                document_version_id,
                f"page:{page.page_number}:chunk:{chunk_index}:sha256:{digest}",
            )
            chunks.append(
                TextChunk(
                    chunk_id=chunk_id,
                    page_number=page.page_number,
                    chunk_index=chunk_index,
                    content=text,
                )
            )
            if start + target_words >= len(words):
                break
    return chunks
