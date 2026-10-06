import codecs
import hashlib
import re
import uuid
from bisect import bisect_left
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from raghub_core.domain.ingestion.limits import MAX_CHUNKS
from raghub_core.domain.ingestion.normalization import NormalizedBlock, SourceSpan
from raghub_core.domain.ingestion.parser import DocumentLimitError, ParsedSection
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
    normalized_content: str | None = None
    embedding_content: str | None = None
    heading_path: tuple[str, ...] = ()
    parent_section_id: uuid.UUID | None = None
    previous_chunk_id: uuid.UUID | None = None
    next_chunk_id: uuid.UUID | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


def embedding_text(chunk):
    return (
        chunk.embedding_content
        if chunk.embedding_content is not None
        else (chunk.normalized_content if chunk.normalized_content is not None else chunk.content)
    )


def _character_offsets(tokens):
    decoder = codecs.getincrementaldecoder("utf-8")()
    offsets = [0]
    for token in tokens:
        offsets.append(
            offsets[-1] + len(decoder.decode(_ENCODING.decode_single_token_bytes(token)))
        )
    return offsets


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
        normalized = isinstance(section, NormalizedBlock)
        text = (
            f"{section.heading}\n\n{section.content}"
            if section.heading and not normalized
            else section.content
        )
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
        if normalized:
            tokens = _ENCODING.encode(text)
            safe_boundaries = _utf8_boundaries(tokens)
            offsets = _character_offsets(tokens)
            boundaries = [
                bisect_left(offsets, match.end())
                for match in re.finditer(r"[.!?](?=\s)|\n\s*\n", text)
            ]
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
                if len(chunks) >= MAX_CHUNKS:
                    raise DocumentLimitError(f"Document exceeds {MAX_CHUNKS} chunks.")
                chunk_index = len(chunks)
                digest = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                section_key = f"{section.section_index}:{section.page_number}:{section.heading}"
                raw = chunk_text
                if normalized:
                    left = (
                        offsets[start]
                        + len(_ENCODING.decode(chunk_tokens))
                        - len(_ENCODING.decode(chunk_tokens).lstrip())
                    )
                    raw = section.raw_slice(left, left + len(chunk_text))
                chunks.append(
                    TextChunk(
                        chunk_id=uuid.uuid5(
                            document_version_id, f"{section_key}:{chunk_index}:{digest}"
                        ),
                        chunk_index=chunk_index,
                        content=raw,
                        token_count=len(_ENCODING.encode(chunk_text)),
                        source_name=section.source_name,
                        page_number=section.page_number,
                        heading=section.heading,
                        content_hash=digest,
                        normalized_content=chunk_text if normalized else None,
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
                (
                    previous.source_name,
                    previous.page_number,
                    previous.heading,
                    getattr(previous, "heading_path", ()),
                    getattr(previous, "type", "paragraph"),
                )
                == (
                    section.source_name,
                    section.page_number,
                    section.heading,
                    getattr(section, "heading_path", ()),
                    getattr(section, "type", "paragraph"),
                )
                and getattr(section, "type", "paragraph") in {"paragraph", "ocr_text"}
                and isinstance(previous, NormalizedBlock) == isinstance(section, NormalizedBlock)
            ):
                extra = {}
                if isinstance(previous, NormalizedBlock) and isinstance(section, NormalizedBlock):
                    normal_shift, raw_shift = (
                        len(previous.content) + 2,
                        len(previous.raw_content) + 2,
                    )
                    extra = {
                        "raw_content": previous.raw_content + "\n\n" + section.raw_content,
                        "source_spans": previous.source_spans
                        + tuple(
                            SourceSpan(
                                s.start + normal_shift,
                                s.end + normal_shift,
                                s.raw_start + raw_shift,
                                s.raw_end + raw_shift,
                            )
                            for s in section.source_spans
                        ),
                    }
                groups[-1] = (
                    replace(previous, content=previous.content + "\n\n" + section.content, **extra),
                    False,
                )
                continue
        groups.append((section, is_table))
    chunks = []
    for section, is_table in groups:
        if is_table:
            pieces = _table_pieces(section, target_tokens)
            produced = []
            for text, row_start, row_end in pieces:
                metadata = dict(getattr(section, "metadata", {}))
                numbers = metadata.get("row_numbers", [])
                metadata.update(
                    row_start=numbers[row_start - 1] if numbers else row_start,
                    row_end=numbers[row_end - 1] if numbers else row_end,
                    header=metadata.get("header", section.content.splitlines()[0]),
                )
                raw = text
                if isinstance(section, NormalizedBlock):
                    lines = section.content.splitlines(keepends=True)
                    header_end = len("".join(lines[:2]))
                    start = len("".join(lines[: row_start + 1]))
                    end = len("".join(lines[: row_end + 2]))
                    raw = (
                        section.raw_slice(0, header_end).rstrip()
                        + "\n"
                        + section.raw_slice(start, end).rstrip()
                    )
                produced.append(
                    TextChunk(
                        uuid.UUID(int=0),
                        0,
                        raw,
                        len(_ENCODING.encode(text)),
                        section.source_name,
                        section.page_number,
                        section.heading,
                        hashlib.sha256(text.encode()).hexdigest(),
                        normalized_content=text if isinstance(section, NormalizedBlock) else None,
                        metadata=metadata,
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
            if len(chunks) >= MAX_CHUNKS:
                raise DocumentLimitError(f"Document exceeds {MAX_CHUNKS} chunks.")
            index = len(chunks)
            key = (
                f"{section.section_index}:{section.page_number}:{section.heading}:"
                f"{index}:{chunk.content_hash}"
            )
            chunks.append(
                replace(
                    chunk,
                    chunk_index=index,
                    chunk_id=uuid.uuid5(document_version_id, key),
                    heading_path=getattr(section, "heading_path", ()),
                    parent_section_id=uuid.uuid5(
                        document_version_id, f"section:{section.section_index}"
                    ),
                    metadata={**getattr(section, "metadata", {}), **chunk.metadata},
                )
            )
    return [
        replace(
            chunk,
            previous_chunk_id=chunks[i - 1].chunk_id if i else None,
            next_chunk_id=chunks[i + 1].chunk_id if i + 1 < len(chunks) else None,
        )
        for i, chunk in enumerate(chunks)
    ]


def _table_pieces(section, target_tokens):
    lines = [line for line in section.content.splitlines() if line.strip()]
    if len(lines) <= 2:
        return [(section.content, 1, max(1, len(lines) - 2))]
    header, rows = lines[:2], lines[2:]
    prefix = section.heading + "\n\n" if section.heading else ""
    pieces, kept = [], []
    start = 1
    for row in rows:
        trial = prefix + "\n".join([*header, *kept, row])
        if kept and len(_ENCODING.encode(trial)) > max(1, target_tokens - 16):
            pieces.append(
                (
                    prefix
                    + f"Rows {start}-{start + len(kept) - 1}\n"
                    + "\n".join([*header, *kept]),
                    start,
                    start + len(kept) - 1,
                )
            )
            start += len(kept)
            kept = []
        kept.append(row)
    if kept:
        pieces.append(
            (
                prefix + f"Rows {start}-{start + len(kept) - 1}\n" + "\n".join([*header, *kept]),
                start,
                start + len(kept) - 1,
            )
        )
    return pieces


chunk_pages = chunk_sections
