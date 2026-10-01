import codecs
import hashlib
import re
import uuid
from dataclasses import dataclass

from app.modules.ingestion.parser import ParsedSection
from app.modules.ingestion.tokenizer import ENCODING

_ENCODING = ENCODING


def _utf8_boundaries(tokens: list[int]) -> set[int]:
    decoder = codecs.getincrementaldecoder("utf-8")()
    safe = {0}
    for index, token in enumerate(tokens, 1):
        decoder.decode(_ENCODING.decode_single_token_bytes(token))
        if not decoder.getstate()[0]:
            safe.add(index)
    return safe


@dataclass(frozen=True, slots=True)
class TextChunk:
    chunk_id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int
    source_name: str
    page_number: int | None
    heading: str | None
    content_hash: str


def chunk_sections(
    sections: list[ParsedSection],
    document_version_id: uuid.UUID,
    *,
    target_tokens: int = 450,
    overlap_tokens: int = 80,
    min_tokens: int = 80,
) -> list[TextChunk]:
    if (
        target_tokens <= 0
        or not 0 <= overlap_tokens < target_tokens
        or not 0 <= min_tokens <= target_tokens
    ):
        raise ValueError("Invalid token chunking parameters.")
    chunks: list[TextChunk] = []
    for section in sections:
        if not section.content.strip():
            continue
        # Keep headings with their own section; never combine pages or different headings.
        text = f"{section.heading}\n\n{section.content}" if section.heading else section.content
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        tokens: list[int] = []
        boundaries: list[int] = []
        for paragraph in paragraphs:
            if tokens:
                tokens.extend(_ENCODING.encode("\n\n"))
            tokens.extend(_ENCODING.encode(paragraph))
            boundaries.append(len(tokens))
        safe_boundaries = _utf8_boundaries(tokens)
        start = 0
        while start < len(tokens):
            end = min(start + target_tokens, len(tokens))
            if end < len(tokens):
                minimum_end = start + max(min_tokens, overlap_tokens + 1)
                suitable = [b for b in boundaries if minimum_end <= b <= end]
                if suitable:
                    end = suitable[-1]
            if len(tokens) - end < min_tokens and end < len(tokens):
                if len(tokens) - start <= target_tokens:
                    end = len(tokens)
                elif len(tokens) - (end - overlap_tokens) < min_tokens:
                    end = max(start + min_tokens, len(tokens) - min_tokens)
            while end not in safe_boundaries and end > start:
                end -= 1
            if end == start:
                end = min(position for position in safe_boundaries if position > start)
            chunk_tokens = tokens[start:end]
            chunk_text = _ENCODING.decode(chunk_tokens).strip()
            if chunk_text:
                chunk_index = len(chunks)
                digest = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                section_key = f"{section.section_index}:{section.page_number}:{section.heading}"
                chunks.append(
                    TextChunk(
                        chunk_id=uuid.uuid5(
                            document_version_id, f"{section_key}:{chunk_index}:{digest}"
                        ),
                        chunk_index=chunk_index,
                        content=chunk_text,
                        token_count=len(_ENCODING.encode(chunk_text)),
                        source_name=section.source_name,
                        page_number=section.page_number,
                        heading=section.heading,
                        content_hash=digest,
                    )
                )
            if end == len(tokens):
                break
            start = max(start + 1, end - overlap_tokens)
            while start not in safe_boundaries:
                start += 1
    return chunks


# Existing callers can migrate without changing the name in one release.
chunk_pages = chunk_sections
