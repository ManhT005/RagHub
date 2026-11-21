"""Conservative search context. Filename hints never become facts about the body."""

import re
import unicodedata
from pathlib import PurePath

CONTEXT_VERSION = "context-v1"
YEAR = re.compile(r"(?<!\d)(?:19|20|21)\d{2}(?!\d)")
EXTENSION = re.compile(r"\.(?:md|markdown|txt|html?|pdf|docx|xlsx)$", re.I)


def years(text):
    return sorted({int(match.group()) for match in YEAR.finditer(text)})


def source_title(name):
    return " ".join(EXTENSION.sub("", PurePath(name).name).replace("_", " ").split())[:1000]


def folded(text):
    text = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    return "".join(c for c in text if not unicodedata.combining(c))


def table_cells(line):
    return [
        cell.strip().replace(r"\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))
    ]


def table_headers(content):
    lines = content.splitlines()
    for i, line in enumerate(lines[:-1]):
        if "|" in line and all(
            re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in table_cells(lines[i + 1])
        ):
            return table_cells(line)
    return []


def search_context(chunk):
    """Return a stable, bounded set of indexable fields for old and new chunks.

    fact_years means years explicitly present in the nearest dated heading/caption
    or table headers, NOT an inferred date for every statement. No body dates or
    filenames are promoted to fact_years. Multiple years remain multiple years.
    """
    metadata = chunk.metadata or {}
    title = source_title(chunk.source_name)
    path = list(chunk.heading_path or ()) or ([chunk.heading] if chunk.heading else [])
    caption = str(metadata.get("table_title") or "")[:1000]
    headers = table_headers(chunk.content)
    is_table = metadata.get("block_type") == "table" or bool(headers)
    # A local caption overrides a parent section, which overrides the filename hint.
    dated_context = next((part for part in [caption, *reversed(path)] if years(part)), "")
    year_source = "table_caption" if caption and years(caption) else "heading_path"
    header_years = years(" ".join(headers))
    fact_years = header_years or years(dated_context)
    doc_years = years(title)
    conflicts = []
    if fact_years and doc_years and not set(fact_years).intersection(doc_years):
        conflicts.append("source_context_year_mismatch")
    codes = set()
    code_columns = [
        i for i, h in enumerate(headers) if re.search(r"\b(ma|code|sku|id|identifier)\b", folded(h))
    ]
    if code_columns:
        for line in chunk.content.splitlines():
            cells = table_cells(line)
            for i in code_columns:
                if i < len(cells) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./-]{1,63}", cells[i]):
                    if any(c.isdigit() for c in cells[i]):
                        codes.add(cells[i].upper())
    return {
        "context_schema_version": CONTEXT_VERSION,
        "source_title": title,
        "section_title": " > ".join(path)[-2000:],
        "table_title": caption or (path[-1][:1000] if is_table and path else ""),
        "table_headers": headers[:64],
        "fact_years": fact_years,
        "document_years": doc_years,
        "entity_codes": sorted(codes)[:128],
        "context_conflicts": conflicts,
        "year_evidence": "table_headers"
        if header_years
        else year_source
        if fact_years
        else "",
    }


def rerank_text(chunk, query=""):
    """Bound metadata separately; preserve the body before truncating long content.

    Keep original source for citations outside this representation. Filename is
    last so rerankers that truncate the tail retain section/table/body evidence.
    """
    ctx = search_context(chunk)
    parts = []
    if ctx["section_title"]:
        parts.append("Section: " + ctx["section_title"][-160:])
    if ctx["table_title"] and ctx["table_title"] != ctx["section_title"]:
        parts.append("Table: " + ctx["table_title"][:160])
    if ctx["table_headers"]:
        parts.append("Columns: " + " | ".join(ctx["table_headers"])[:200])
    # Cross-encoders often truncate at 512 tokens. Show matching intact table
    # rows before the full body, so a long table cannot hide its relevant row.
    if ctx["table_headers"] and query:
        terms = set(re.findall(r"[^\W_]+", folded(query))) - {
            "la",
            "bao",
            "nhieu",
            "cho",
            "toi",
            "biet",
            "nam",
            "the",
            "what",
            "is",
            "of",
        }
        terms -= {str(y) for y in years(query)}
        rows = []
        for position, line in enumerate(chunk.content.splitlines()):
            if "|" not in line or re.search(r"\|\s*:?-{3,}", line):
                continue
            if table_cells(line) == ctx["table_headers"]:
                continue
            words = set(re.findall(r"[^\W_]+", folded(line)))
            overlap = len(terms & words)
            if overlap:
                rows.append((overlap, -position, line))
        if rows:
            parts.append(
                "Matching table rows:\n"
                + "\n".join(r[2] for r in sorted(rows, reverse=True)[:2])[:2000]
            )
    parts.append("Content:\n" + chunk.content[:16000])
    parts.append("Source filename (may differ from content): " + ctx["source_title"][:300])
    return "\n".join(parts)
