"""DOCX adapter: paragraphs and tables in document order via python-docx."""

from __future__ import annotations

import io

import docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from raghub_core.domain.ingestion.limits import (
    check_compressed_size,
    check_signature,
    check_zip_container,
)
from raghub_core.domain.ingestion.parser import EmptyExtractedTextError, ParsedBlock, ParsedSection


def _list_info(paragraph, document):
    props = paragraph._p.find("./" + qn("w:pPr") + "/" + qn("w:numPr"))
    if props is None and paragraph.style is not None:
        props = paragraph.style.element.find("./" + qn("w:pPr") + "/" + qn("w:numPr"))
    if props is None:
        return None
    number = props.find(qn("w:numId"))
    indent = props.find(qn("w:ilvl"))
    level = int(indent.get(qn("w:val"))) if indent is not None else 0
    number_id = number.get(qn("w:val")) if number is not None else "0"
    definitions = document.part.numbering_part.element
    abstract_id = None
    override_start = None
    for item in definitions.findall(qn("w:num")):
        if item.get(qn("w:numId")) == number_id:
            node = item.find(qn("w:abstractNumId"))
            abstract_id = node.get(qn("w:val")) if node is not None else None
            for override in item.findall(qn("w:lvlOverride")):
                if override.get(qn("w:ilvl")) == str(level):
                    start = override.find(qn("w:startOverride"))
                    if start is not None:
                        override_start = int(start.get(qn("w:val")))
    for abstract in definitions.findall(qn("w:abstractNum")):
        if abstract.get(qn("w:abstractNumId")) == abstract_id:
            for item in abstract.findall(qn("w:lvl")):
                if item.get(qn("w:ilvl")) == str(level):
                    fmt = item.find(qn("w:numFmt"))
                    start = item.find(qn("w:start"))
                    start_number = int(start.get(qn("w:val"))) if start is not None else 1
                    return (
                        level,
                        number_id,
                        fmt is not None and fmt.get(qn("w:val")) not in {"bullet", "none"},
                        override_start if override_start is not None else start_number,
                    )
    return level, number_id, False, 1


def parse_docx(
    content: bytes, source_name: str = "document.docx", *, structured=False
) -> list[ParsedSection]:
    check_compressed_size(len(content))
    check_signature(content, ".docx")
    check_zip_container(content, ".docx")
    try:
        document = docx.Document(io.BytesIO(content))
    except Exception as exc:
        raise EmptyExtractedTextError("The DOCX file cannot be opened.") from exc
    sections: list[ParsedSection] = []
    table_index = 0
    path: list[str] = []
    list_counters = {}
    levels = []
    paragraph_index = 0
    for block in document.element.body:
        tag = block.tag.split("}")[-1]
        if tag == "p":
            paragraph = Paragraph(block, document)
            text = paragraph.text.strip()
            paragraph_index += 1
            if text:
                style = paragraph.style.name if paragraph.style else ""
                heading = style.startswith("Heading ") and style[8:].isdigit()
                outline = paragraph._p.find("./" + qn("w:pPr") + "/" + qn("w:outlineLvl"))
                if structured and outline is not None:
                    heading = True
                if heading:
                    level = (
                        max(1, int(outline.get(qn("w:val"))) + 1)
                        if structured and outline is not None
                        else max(1, int(style[8:]))
                    )
                    if structured:
                        while levels and levels[-1][0] >= level:
                            levels.pop()
                        levels.append((level, text))
                        path = [label for _, label in levels]
                    else:
                        path = path[: level - 1] + [text]
                info = _list_info(paragraph, document) if structured else None
                is_list = structured and (info is not None or style.lower().startswith("list"))
                if is_list:
                    indent, number_id, ordered, start_number = info or (
                        0,
                        style,
                        "number" in style.lower(),
                        1,
                    )
                    key = (number_id, indent)
                    list_counters[key] = list_counters.get(key, start_number - 1) + 1
                    text = (
                        "  " * min(indent, 8)
                        + (f"{list_counters[key]}. " if ordered else "- ")
                        + text
                    )
                else:
                    list_counters.clear()
                code = structured and "code" in style.lower()
                if code:
                    text = paragraph.text.rstrip("\r\n")
                sections.append(
                    ParsedBlock(
                        text,
                        source_name,
                        len(sections),
                        heading=" / ".join(path) or None,
                        type="heading"
                        if heading
                        else "list"
                        if is_list
                        else "code"
                        if code
                        else "paragraph",
                        heading_path=tuple(path),
                        metadata={"format": "docx", "paragraph_index": paragraph_index}
                        if structured
                        else {},
                    )
                )
        elif tag == "tbl":
            table = Table(block, document)
            rows = [
                "| "
                + " | ".join(
                    cell.text.strip().replace("|", "/").replace("\n", " ") for cell in row.cells
                )
                + " |"
                for row in table.rows
            ]
            if structured:
                rows = []
                for row in table.rows:
                    seen, values = set(), []
                    for cell in row.cells:
                        text = cell.text.strip().replace("|", "\\|").replace("\n", " ")
                        values.append("" if cell._tc in seen else text)
                        seen.add(cell._tc)
                    rows.append("| " + " | ".join(values) + " |")
            rows = [row for row in rows if row.strip("| ").strip()]
            if rows:
                width = (
                    max(len(row.cells) for row in table.rows)
                    if structured
                    else max(row.count("|") - 1 for row in rows)
                )
                lines = [rows[0], "| " + " | ".join(["---"] * width) + " |", *rows[1:]]
                sections.append(
                    ParsedBlock(
                        "\n".join(lines),
                        source_name,
                        len(sections),
                        heading=" / ".join([*path, f"Table {table_index + 1}"]),
                        type="table",
                        heading_path=tuple(path),
                        metadata={"format": "docx", "table_index": table_index + 1}
                        if structured
                        else {},
                    )
                )
                table_index += 1
    if not sections:
        raise EmptyExtractedTextError("The DOCX file contains no text.")
    return sections
