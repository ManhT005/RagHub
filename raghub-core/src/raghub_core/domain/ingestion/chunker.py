import codecs
import hashlib
import re
import uuid
from dataclasses import dataclass, replace

from raghub_core.domain.ingestion.parser import ParsedSection
from raghub_core.domain.ingestion.tokenizer import ENCODING

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


def _chunk_text_sections(
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
            sentences = re.split(r"(?<=[.!?])(?=\s)", paragraph)
            for sentence in sentences:
                tokens.extend(_ENCODING.encode(sentence))
                boundaries.append(len(tokens))
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


def chunk_sections(
    sections, document_version_id, *, target_tokens=450, overlap_tokens=60, min_tokens=80
):
    if (
        target_tokens <= 0
        or not 0 <= overlap_tokens < target_tokens
        or not 0 <= min_tokens <= target_tokens
    ):
        raise ValueError("Invalid token chunking parameters.")
    groups = []
    for section in sections:
        if not section.content.strip() or getattr(section, "type", "paragraph") == "heading":
            continue
        is_table = getattr(section, "type", "") == "table"
        if not is_table:
            lines = section.content.splitlines()
            is_table = len(lines) > 1 and bool(re.match(r"^\s*\|[ :|-]+\|\s*$", lines[1]))
        if groups and not is_table and not groups[-1][1]:
            previous = groups[-1][0]
            if (
                previous.source_name,
                previous.page_number,
                previous.heading,
                getattr(previous, "heading_path", ()),
            ) == (
                section.source_name,
                section.page_number,
                section.heading,
                getattr(section, "heading_path", ()),
            ):
                groups[-1] = (
                    replace(previous, content=previous.content + "\n\n" + section.content),
                    False,
                )
                continue
        groups.append((section, is_table))
    chunks = []
    for section, is_table in groups:
        if is_table:
            pieces = _table_pieces(section, target_tokens)
            produced = []
            for text in pieces:
                produced.append(
                    TextChunk(
                        uuid.UUID(int=0),
                        0,
                        text,
                        len(_ENCODING.encode(text)),
                        section.source_name,
                        section.page_number,
                        section.heading,
                        hashlib.sha256(text.encode()).hexdigest(),
                    )
                )
        else:
            produced = _chunk_text_sections(
                [section],
                document_version_id,
                target_tokens=target_tokens,
                overlap_tokens=overlap_tokens,
                min_tokens=min_tokens,
            )
        for chunk in produced:
            index = len(chunks)
            key = f"{section.section_index}:{section.page_number}:{section.heading}:{index}:{chunk.content_hash}"
            chunks.append(
                replace(chunk, chunk_index=index, chunk_id=uuid.uuid5(document_version_id, key))
            )
    return chunks


def _table_pieces(section, target_tokens):
    lines = [line for line in section.content.splitlines() if line.strip()]
    if len(lines) <= 2:
        return [section.content]
    header, rows = lines[:2], lines[2:]
    prefix = section.heading + "\n\n" if section.heading else ""
    pieces, kept = [], []
    start = 1
    for row in rows:
        trial = prefix + "\n".join([*header, *kept, row])
        if kept and len(_ENCODING.encode(trial)) > max(1, target_tokens - 16):
            pieces.append(
                prefix + f"Rows {start}-{start + len(kept) - 1}\n" + "\n".join([*header, *kept])
            )
            start += len(kept)
            kept = []
        kept.append(row)
    if kept:
        pieces.append(
            prefix + f"Rows {start}-{start + len(kept) - 1}\n" + "\n".join([*header, *kept])
        )
    return pieces


chunk_pages = chunk_sections
