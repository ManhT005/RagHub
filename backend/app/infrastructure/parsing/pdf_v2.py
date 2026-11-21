"""Position-aware PDF blocks and conservative repeated-margin removal."""

import math
import re
from collections import defaultdict

import pymupdf
from raghub_core.domain.ingestion.parser import ParsedBlock


def page_blocks(page, source_name, start):
    tables = []
    warnings = []
    try:
        detected = page.find_tables().tables
    except Exception:
        detected = []
        warnings.append("TABLE_DETECTION_FAILED")
    for number, table in enumerate(detected, 1):
        rows = [
            [str(value or "").strip().replace("|", "\\|").replace("\n", " ") for value in row]
            for row in table.extract()
        ]
        if not rows or not any(any(row) for row in rows):
            continue
        width = max(map(len, rows))
        rows = [row + [""] * (width - len(row)) for row in rows]
        text = "\n".join(
            "| " + " | ".join(row) + " |" for row in [rows[0], ["---"] * width, *rows[1:]]
        )
        tables.append((pymupdf.Rect(table.bbox), text, number))
    blocks = []
    for row in page.get_text("blocks"):
        if row[6] != 0 or not row[4].strip():
            continue
        box = pymupdf.Rect(row[:4])
        if any((box & bounds).get_area() >= box.get_area() * 0.8 for bounds, _, _ in tables):
            continue
        blocks.append((box, row[4].strip(), "paragraph", {}))
    blocks.extend((box, text, "table", {"table_index": number}) for box, text, number in tables)
    middle = page.cropbox.width / 2
    left = [b for b in blocks if b[0].x1 <= middle + 5]
    right = [b for b in blocks if b[0].x0 >= middle - 5]
    columns = len(left) >= 2 and len(right) >= 2
    if columns:
        full = sorted(
            [b for b in blocks if b not in left and b not in right], key=lambda b: b[0].y0
        )
        ordered, remaining = [], [b for b in blocks if b in left or b in right]
        for barrier in full:
            band = [b for b in remaining if b[0].y0 < barrier[0].y0]
            ordered.extend(sorted(band, key=lambda b: (b[0].x0 >= middle - 5, b[0].y0)))
            remaining = [b for b in remaining if b not in band]
            ordered.append(barrier)
        ordered.extend(sorted(remaining, key=lambda b: (b[0].x0 >= middle - 5, b[0].y0)))
    else:
        ordered = sorted(blocks, key=lambda b: (b[0].y0, b[0].x0))
    result = []
    for box, text, kind, metadata in ordered:
        quality = list(warnings)
        if kind == "paragraph" and ("\ufffd" in text or sum(ch.isalnum() for ch in text) < 8):
            quality.append("LOW_TEXT_QUALITY")
        if kind == "paragraph":
            text = re.sub(r"(?<=[^\W\d_])-\n(?=[a-zà-ỹ])", "", text)
        result.append(
            ParsedBlock(
                text,
                source_name,
                start + len(result),
                page.number + 1,
                type=kind,
                metadata={
                    "format": "pdf",
                    "bbox": list(box),
                    "page_height": page.cropbox.height,
                    "reading_order": "two-column" if columns else "position",
                "quality_warnings": quality,
                    **metadata,
                },
            )
        )
    return result


def remove_repeated_margins(blocks, page_count):
    candidates = defaultdict(set)
    for block in blocks:
        box = block.metadata.get("bbox")
        height = block.metadata.get("page_height", 0)
        if block.type != "paragraph" or not box or not height:
            continue
        if (box[3] < height * 0.12 or box[1] > height * 0.88) and len(block.content) <= 160:
            label = re.sub(r"(?i)\b(page|trang)\s+\d+(?:\s*/\s*\d+)?", r"\1 #", block.content)
            candidates[label].add(block.page_number)
    repeated = {
        label
        for label, pages in candidates.items()
        if len(pages) >= max(3, math.ceil(page_count * 0.6))
    }
    result = []
    for block in blocks:
        box = block.metadata.get("bbox")
        height = block.metadata.get("page_height", 0)
        label = re.sub(r"(?i)\b(page|trang)\s+\d+(?:\s*/\s*\d+)?", r"\1 #", block.content)
        if box and (box[3] < height * 0.12 or box[1] > height * 0.88) and label in repeated:
            continue
        result.append(block)
    return result
