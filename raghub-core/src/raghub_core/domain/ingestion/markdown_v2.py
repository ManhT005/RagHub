"""Opt-in Markdown blocks and bounded chunks; never executes front matter or code."""

import hashlib
import re
import uuid
from dataclasses import replace

from raghub_core.domain.ingestion.chunker import TextChunk
from raghub_core.domain.ingestion.limits import MAX_CHUNKS
from raghub_core.domain.ingestion.parser import (
    DocumentLimitError,
    EmptyExtractedTextError,
    ParsedBlock,
    _decode,
)
from raghub_core.domain.ingestion.tokenizer import ENCODING
from raghub_core.domain.retrieval.context import search_context

VERSION = "markdown-v2"
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)\s*$")
LIST = re.compile(r"^ {0,3}(?:[-+*]|\d+[.)])[ \t]+")


def _table_separator(line):
    cells = line.strip().strip("|").split("|")
    return bool(cells) and all(re.fullmatch(r"\s*:?-{3,}:?\s*", c) for c in cells)


def parse_markdown_blocks(content, source_name):
    lines = _decode(content).splitlines()
    blocks, headings = [], []
    i = 0
    section_line = 0
    title = None
    # Only a leading, delimited key/value front matter block is metadata.
    if lines and lines[0].strip() == "---":
        end = next((j for j in range(1, min(len(lines), 100)) if lines[j].strip() == "---"), None)
        if end and any(re.match(r"^[\w-]+:\s*", line) for line in lines[1:end]):
            title_line = next((line for line in lines[1:end] if line.startswith("title:")), "")
            title = title_line.partition(":")[2].strip().strip("\"'") or None
            i = end + 1

    def emit(kind, start, end, **extra):
        text = "\n".join(lines[start:end])
        if not text.strip():
            return
        path = tuple(label for _, label in headings)
        blocks.append(
            ParsedBlock(
                text,
                source_name,
                len(blocks),
                heading=" / ".join(path) or None,
                type=kind,
                heading_path=path,
                metadata={
                    "format": "markdown",
                    "document_pipeline": VERSION,
                    "line_start": start + 1,
                    "line_end": end,
                    "section_line": section_line,
                    **({"document_title": title} if title else {}),
                    **extra,
                },
            )
        )

    def table_at(position):
        return (
            position + 1 < len(lines)
            and "|" in lines[position]
            and _table_separator(lines[position + 1])
        )

    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        start = i
        fence = FENCE.match(lines[i])
        if fence:
            marker = fence.group(1)
            i += 1
            while i < len(lines):
                close = FENCE.match(lines[i])
                i += 1
                if (
                    close
                    and close.group(1)[0] == marker[0]
                    and len(close.group(1)) >= len(marker)
                    and not close.group(2).strip()
                ):
                    break
            else:
                emit("code", start, i, fence=marker, unclosed_fence=True)
                continue
            emit("code", start, i, fence=marker)
            continue
        match = HEADING.match(lines[i])
        setext = i + 1 < len(lines) and re.fullmatch(r" {0,3}(=+|-+)\s*", lines[i + 1])
        if match or setext:
            section_line = start + 1
            level = (
                len(match.group(1)) if match else 1 if lines[i + 1].lstrip().startswith("=") else 2
            )
            label = re.sub(r"\s+#+\s*$", "", match.group(2)) if match else lines[i].strip()
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, label))
            i += 1 if match else 2
            emit("heading", start, i)
            continue
        if table_at(i):
            i += 2
            while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                i += 1
            emit("table", start, i)
            continue
        if LIST.match(lines[i]):
            i += 1
            while i < len(lines):
                if not lines[i].strip():
                    following = i + 1
                    while following < len(lines) and not lines[following].strip():
                        following += 1
                    if following < len(lines) and (
                        LIST.match(lines[following]) or lines[following].startswith((" ", "\t"))
                    ):
                        i = following
                        continue
                    break
                if HEADING.match(lines[i]) or FENCE.match(lines[i]) or table_at(i):
                    break
                i += 1
            emit("list", start, i)
            continue
        i += 1
        while i < len(lines) and lines[i].strip():
            if (
                HEADING.match(lines[i])
                or FENCE.match(lines[i])
                or LIST.match(lines[i])
                or table_at(i)
            ):
                break
            if i + 1 < len(lines) and re.fullmatch(r" {0,3}(=+|-+)\s*", lines[i + 1]):
                break
            i += 1
        emit("paragraph", start, i)
    if not any(b.type != "heading" for b in blocks):
        raise EmptyExtractedTextError("Markdown has no body content.")
    return blocks


def _split_exact(text, budget, *, paragraph=False):
    """Split oversized blocks without dropping characters or breaking Unicode."""
    while text:
        if len(ENCODING.encode(text)) <= budget:
            yield text
            return
        lo, hi = 1, len(text)
        while lo < hi:
            middle = (lo + hi + 1) // 2
            if len(ENCODING.encode(text[:middle])) <= budget:
                lo = middle
            else:
                hi = middle - 1
        if len(ENCODING.encode(text[:lo])) > budget:
            raise DocumentLimitError("Markdown context leaves no room for body text.")
        newline = text.rfind("\n", 0, lo)
        if newline >= lo // 2:
            lo = newline + 1
        elif paragraph:
            sentence_ends = [m.end() for m in re.finditer(r"(?<=[.!?])\s+", text[:lo])]
            word_ends = [m.end() for m in re.finditer(r"\s+", text[:lo])]
            for boundaries in (sentence_ends, word_ends):
                if boundaries and boundaries[-1] >= lo // 2:
                    lo = boundaries[-1]
                    break
        yield text[:lo]
        text = text[lo:]


def _pack(units, budget, prefix="", suffix=""):
    kept, begin = [], 1
    for position, unit in enumerate(units, 1):
        if len(ENCODING.encode(prefix + unit + suffix)) > budget:
            if kept:
                yield (
                    prefix + "\n".join(kept) + suffix,
                    {"unit_start": begin, "unit_end": position - 1},
                )
                kept = []
            allowance = budget - len(ENCODING.encode(prefix + suffix)) - 4
            if allowance < 1:
                raise DocumentLimitError("Markdown block header exceeds token budget.")
            for fragment in _split_exact(unit, allowance):
                yield (
                    prefix + fragment + suffix,
                    {"unit_start": position, "unit_end": position, "structural_split": True},
                )
            begin = position + 1
            continue
        if kept and len(ENCODING.encode(prefix + "\n".join([*kept, unit]) + suffix)) > budget:
            yield prefix + "\n".join(kept) + suffix, {"unit_start": begin, "unit_end": position - 1}
            kept = []
            begin = position
        kept.append(unit)
    if kept:
        yield prefix + "\n".join(kept) + suffix, {"unit_start": begin, "unit_end": len(units)}


def chunk_markdown_blocks(blocks, document_version_id, *, target_tokens=450, pipeline=VERSION):
    merged = []
    previous = None
    enriched = []
    for block in blocks:
        # A short caption immediately before a table is local evidence. Never
        # borrow prose across a page/section, or use a filename as a caption.
        if (
            block.type == "table"
            and previous is not None
            and previous.type in {"paragraph", "list"}
            and previous.source_name == block.source_name
            and previous.page_number == block.page_number
            and previous.heading_path == block.heading_path
            and len(previous.content) <= 240
            and len(previous.content.splitlines()) <= 2
            and (
                previous.content.rstrip().endswith(":")
                or re.match(r"^\s*\d+[.)]\s+", previous.content)
            )
        ):
            block = replace(
                block, metadata={**block.metadata, "table_title": previous.content.strip()}
            )
        enriched.append(block)
        previous = block
    for block in enriched:
        if (
            merged
            and block.type == merged[-1].type
            and block.type
            in ({"paragraph", "list"} if pipeline == "document-v2" else {"paragraph"})
            and block.heading_path == merged[-1].heading_path
            and block.source_name == merged[-1].source_name
            and block.page_number == merged[-1].page_number
            and block.metadata.get("section_line") == merged[-1].metadata.get("section_line")
        ):
            previous = merged[-1]
            merged[-1] = replace(
                previous,
                content=previous.content + "\n\n" + block.content,
                metadata={**previous.metadata, "line_end": block.metadata.get("line_end")},
            )
        else:
            merged.append(block)
    result = []
    for block in merged:
        if block.type == "heading":
            continue
        context = f"Source: {block.source_name}\n"
        if block.heading_path:
            context += "Section: " + " > ".join(block.heading_path) + "\n"
        if block.page_number is not None:
            context += f"Page: {block.page_number}\n"
        context += "\n"
        budget = target_tokens - len(ENCODING.encode(context)) - 8
        if budget < 16:
            raise DocumentLimitError("Markdown source/heading context exceeds token budget.")
        if block.type == "table":
            lines = block.content.splitlines()
            header = "\n".join(lines[:2]) + "\n"
            # A huge row must not silently turn into broken columns.
            if any(len(ENCODING.encode(header + row)) > budget for row in lines[2:]):
                raise DocumentLimitError(
                    "Markdown table row exceeds chunk budget; shorten or split the row."
                )
            pieces = (
                list(_pack(lines[2:], budget, prefix=header))
                if len(lines) > 2
                else [(block.content, {})]
            )
        elif block.type == "code" and block.metadata.get("fence"):
            lines = block.content.splitlines()
            body = lines[1:] if block.metadata.get("unclosed_fence") else lines[1:-1]
            pieces = list(
                _pack(body, budget, prefix=lines[0] + "\n", suffix="\n" + block.metadata["fence"])
            )
            pieces = [(text, {**meta, "synthetic_fences": True}) for text, meta in pieces]
            if not pieces:
                pieces = [(block.content, {})]
        elif block.type == "code":
            pieces = list(_pack(block.content.splitlines(), budget))
        elif block.type == "list":
            items = []
            base_indent = len(block.content) - len(block.content.lstrip(" "))
            for line in block.content.splitlines():
                indent = len(line) - len(line.lstrip(" "))
                if (LIST.match(line) and indent <= base_indent) or not items:
                    items.append(line)
                else:
                    items[-1] += "\n" + line
            pieces = list(_pack(items, budget))
        else:
            fragments = list(_split_exact(block.content, budget, paragraph=True))
            pieces = [(text, {"structural_split": len(fragments) > 1}) for text in fragments]
        for text, metadata in pieces:
            if len(result) >= MAX_CHUNKS:
                raise DocumentLimitError(f"Document exceeds {MAX_CHUNKS} chunks.")
            embedded = context + text
            if len(ENCODING.encode(embedded)) > target_tokens:
                raise DocumentLimitError("Markdown chunk exceeds embedding token budget.")
            digest = hashlib.sha256(text.encode()).hexdigest()
            index = len(result)
            section_key = block.metadata.get("section_line", block.section_index)
            if (
                block.type == "table"
                and block.metadata.get("row_numbers")
                and "unit_start" in metadata
            ):
                numbers = block.metadata["row_numbers"]
                metadata = {
                    **metadata,
                    "row_start": numbers[metadata["unit_start"] - 1],
                    "row_end": numbers[metadata["unit_end"] - 1],
                }
            result.append(
                TextChunk(
                    uuid.uuid5(document_version_id, f"{pipeline}:{index}:{digest}"),
                    index,
                    text,
                    len(ENCODING.encode(text)),
                    block.source_name,
                    block.page_number,
                    block.heading,
                    digest,
                    embedding_content=embedded,
                    heading_path=block.heading_path,
                    parent_section_id=uuid.uuid5(
                        document_version_id,
                        f"heading:{block.page_number}:{section_key}:"
                        + " > ".join(block.heading_path),
                    ),
                    metadata={
                        **block.metadata,
                        "block_type": block.type,
                        **metadata,
                        "document_pipeline": pipeline,
                    },
                )
            )
    return [
        replace(
            c,
            metadata={**c.metadata, "search_context": search_context(c)},
            previous_chunk_id=result[i - 1].chunk_id if i else None,
            next_chunk_id=result[i + 1].chunk_id if i + 1 < len(result) else None,
        )
        for i, c in enumerate(result)
    ]
