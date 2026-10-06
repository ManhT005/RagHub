"""DOCX adapter: paragraphs and tables in document order via python-docx."""

from __future__ import annotations

import io

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph
from raghub_core.domain.ingestion.limits import (
    check_compressed_size,
    check_signature,
    check_zip_container,
)
from raghub_core.domain.ingestion.parser import EmptyExtractedTextError, ParsedBlock, ParsedSection


def parse_docx(content: bytes, source_name: str = "document.docx") -> list[ParsedSection]:
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
    for block in document.element.body:
        tag = block.tag.split("}")[-1]
        if tag == "p":
            paragraph = Paragraph(block, document)
            text = paragraph.text.strip()
            if text:
                style = paragraph.style.name if paragraph.style else ""
                heading = style.startswith("Heading ") and style[8:].isdigit()
                if heading:
                    level = max(1, int(style[8:]))
                    path = path[: level - 1] + [text]
                sections.append(
                    ParsedBlock(
                        text,
                        source_name,
                        len(sections),
                        heading=" / ".join(path) or None,
                        type="heading" if heading else "paragraph",
                        heading_path=tuple(path),
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
            rows = [row for row in rows if row.strip("| ").strip()]
            if rows:
                width = max(row.count("|") - 1 for row in rows)
                lines = [rows[0], "| " + " | ".join(["---"] * width) + " |", *rows[1:]]
                sections.append(
                    ParsedBlock(
                        "\n".join(lines),
                        source_name,
                        len(sections),
                        heading=" / ".join([*path, f"Table {table_index + 1}"]),
                        type="table",
                        heading_path=tuple(path),
                    )
                )
                table_index += 1
    if not sections:
        raise EmptyExtractedTextError("The DOCX file contains no text.")
    return sections
