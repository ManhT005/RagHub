"""Deterministic document normalization with offsets back to the source text."""

import hashlib
import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from raghub_core.domain.ingestion.parser import ParsedBlock

NORMALIZATION_VERSION = "normalized-v1"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start: int
    end: int
    raw_start: int
    raw_end: int


@dataclass(frozen=True, slots=True)
class NormalizedBlock(ParsedBlock):
    raw_content: str = ""
    content_hash: str = ""
    source_spans: tuple[SourceSpan, ...] = ()

    def raw_slice(self, start: int, end: int) -> str:
        spans = [s for s in self.source_spans if s.end > start and s.start < end]
        if not spans:
            return ""

        def offset(span, position, upper):
            if span.end - span.start == span.raw_end - span.raw_start:
                return span.raw_start + max(0, min(position - span.start, span.end - span.start))
            return span.raw_end if upper else span.raw_start

        return self.raw_content[offset(spans[0], start, False) : offset(spans[-1], end, True)]


def _margin_ranges(blocks):
    """Only repeated outer lines of PDF pages with enough body text are candidates."""
    candidates = defaultdict(set)
    ranges = defaultdict(list)
    pages = {b.page_number for b in blocks if b.metadata.get("format") == "pdf"}
    for i, block in enumerate(blocks):
        if block.metadata.get("format") != "pdf" or block.type != "paragraph":
            continue
        lines = list(re.finditer(r"[^\r\n]+", block.content))
        lines = [line for line in lines if line.group().strip()]
        if len(lines) < 4:
            continue
        for side, line in (("header", lines[0]), ("footer", lines[-1])):
            label = unicodedata.normalize("NFC", line.group()).strip()
            # Match page counters only when explicitly labelled; don't erase numeric facts.
            label = re.sub(r"(?i)\b(page|trang)\s+\d+(?:\s*/\s*\d+)?\b", r"\1 #", label)
            if len(label) <= 160:
                key = (block.source_name, side, label)
                candidates[key].add(block.page_number)
                ranges[i].append((key, line.start(), line.end()))
    threshold = max(3, math.ceil(len(pages) * 0.6))
    return {
        i: [(a, b) for key, a, b in entries if len(candidates[key]) >= threshold]
        for i, entries in ranges.items()
    }


def normalize_block(block, *, excluded=()) -> NormalizedBlock:
    raw = block.content
    kind = getattr(block, "type", "paragraph")
    removed = list(excluded)
    if block.page_number is not None and kind in {"paragraph", "ocr_text"}:
        for match in re.finditer(r"[^\W\d_]{2,}(-\r?\n[ \t]*)(?=[^\W\d_])", raw):
            removed.append(match.span(1))
    # Process runs outside deleted margins/line-wrap hyphens without losing offsets.
    removed.sort()
    pieces, position = [], 0
    for start, end in removed:
        if start >= position:
            pieces.append((position, raw[position:start]))
        position = max(position, end)
    pieces.append((position, raw[position:]))
    text, spans = [], []
    length = 0
    for base, piece in pieces:
        for match in re.finditer(r"\s+|\S+", piece):
            value = match.group()
            if value.isspace() and kind != "code":
                value = "\n\n" if value.count("\n") >= 2 else "\n" if "\n" in value else " "
            else:
                value = unicodedata.normalize("NFC", value.replace("\r\n", "\n"))
            text.append(value)
            spans.append(
                SourceSpan(length, length + len(value), base + match.start(), base + match.end())
            )
            length += len(value)
    normalized = "".join(text)
    left = len(normalized) - len(normalized.lstrip())
    normalized = normalized.strip()
    spans = tuple(
        SourceSpan(
            max(0, s.start - left), min(len(normalized), s.end - left), s.raw_start, s.raw_end
        )
        for s in spans
        if s.end > left and s.start < left + len(normalized)
    )
    return NormalizedBlock(
        content=normalized,
        source_name=block.source_name,
        section_index=block.section_index,
        page_number=block.page_number,
        heading=block.heading,
        type=kind,
        heading_path=getattr(block, "heading_path", ()),
        metadata={**getattr(block, "metadata", {}), "normalization_version": NORMALIZATION_VERSION},
        raw_content=raw,
        content_hash=hashlib.sha256(normalized.encode()).hexdigest(),
        source_spans=spans,
    )


def normalize_sections(sections):
    blocks = [
        b
        if isinstance(b, ParsedBlock)
        else ParsedBlock(b.content, b.source_name, b.section_index, b.page_number, b.heading)
        for b in sections
    ]
    margins = _margin_ranges(blocks)
    result, seen = [], set()
    for i, block in enumerate(blocks):
        normalized = normalize_block(block, excluded=margins.get(i, ()))
        identity = (
            block.source_name,
            block.page_number,
            block.heading_path,
            block.type,
            normalized.content_hash,
        )
        # Tables and list items can intentionally repeat; preserve every row/item.
        if not normalized.content or (identity in seen and block.type == "paragraph"):
            continue
        seen.add(identity)
        result.append(normalized)
    return result
