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
from raghub_core.domain.ingestion.parser import EmptyExtractedTextError, ParsedSection


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
    for block in document.element.body:
        tag = block.tag.split("}")[-1]
        if tag == "p":
            text = Paragraph(block, document).text.strip()
            if text:
                sections.append(ParsedSection(text, source_name, len(sections)))
        elif tag == "tbl":
            table = Table(block, document)
            rows = [
                "| " + " | ".join(cell.text.strip() for cell in row.cells) + " |"
                for row in table.rows
            ]
            rows = [row for row in rows if row.strip("| ").strip()]
            if rows:
                width = max(row.count("|") - 1 for row in rows)
                lines = [rows[0], "| " + " | ".join(["---"] * width) + " |", *rows[1:]]
                sections.append(
                    ParsedSection(
                        "\n".join(lines),
                        source_name,
                        len(sections),
                        heading=f"Table {table_index + 1}",
                    )
                )
                table_index += 1
    if not sections:
        raise EmptyExtractedTextError("The DOCX file contains no text.")
    return sections
