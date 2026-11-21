"""UTF-8 text blocks with source lines and diagnostic warnings."""

import re

from raghub_core.domain.ingestion.parser import (
    EmptyExtractedTextError,
    ParsedBlock,
    TextDecodeError,
    _decode,
)


def parse_text_blocks(content, source_name):
    text = _decode(content)
    if "\x00" in text:
        raise TextDecodeError("Text contains NUL bytes; provide a UTF-8 text file.")
    lines = text.splitlines()
    blocks, start = [], 0
    for end in range(len(lines) + 1):
        if end < len(lines) and lines[end].strip():
            continue
        if start < end:
            body = "\n".join(lines[start:end])
            warnings = ["REPLACEMENT_CHARACTERS"] if "\ufffd" in body else []
            kind = "list" if re.match(r"^\s*(?:[-+*]|\d+[.)])\s", body) else "paragraph"
            blocks.append(
                ParsedBlock(
                    body,
                    source_name,
                    len(blocks),
                    type=kind,
                    metadata={
                        "format": "txt",
                        "line_start": start + 1,
                        "line_end": end,
                        "quality_warnings": warnings,
                    },
                )
            )
        start = end + 1
    if not blocks:
        raise EmptyExtractedTextError("Text contains no body content.")
    return blocks
