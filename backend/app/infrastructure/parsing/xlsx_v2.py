"""Offline workbook tables separated by blank rows; formulas are never evaluated."""

import io
import re

import openpyxl
from raghub_core.domain.ingestion.limits import MAX_POPULATED_CELLS, MAX_SHEETS
from raghub_core.domain.ingestion.parser import (
    DocumentLimitError,
    EmptyExtractedTextError,
    ParsedBlock,
)


def parse_workbook(content, source_name):
    books = []
    try:
        for data_only in (True, False):
            books.append(
                openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=data_only)
            )
        if len(books[0].sheetnames) > MAX_SHEETS:
            raise DocumentLimitError(f"Workbook exceeds {MAX_SHEETS} sheets.")
        blocks, cells = [], 0
        for sheet in books[0]:
            rows, groups, missing = [], [], []
            if (sheet.max_row or 0) * (sheet.max_column or 0) > MAX_POPULATED_CELLS * 20:
                raise DocumentLimitError("Spreadsheet grid is too sparse/large to scan safely.")
            formulas = books[1][sheet.title]
            for row_number, (row, formula_row) in enumerate(
                zip(sheet.iter_rows(), formulas.iter_rows(), strict=True), 1
            ):
                values = []
                for cell, formula in zip(row, formula_row, strict=True):
                    if formula.data_type == "f" and cell.value is None:
                        if len(missing) < 100:
                            missing.append(formula.coordinate)
                    value = cell.value
                    values.append(
                        ""
                        if value is None
                        else str(value).strip().replace("|", "\\|").replace("\n", " ")
                    )
                    cells += value is not None or formula.data_type == "f"
                    if cells > MAX_POPULATED_CELLS:
                        raise DocumentLimitError(
                            f"Workbook exceeds {MAX_POPULATED_CELLS} populated cells."
                        )
                while values and not values[-1]:
                    values.pop()
                if any(values):
                    rows.append((row_number, values))
                elif rows:
                    groups.append(rows)
                    rows = []
            if rows:
                groups.append(rows)
            for number, group in enumerate(groups, 1):
                width = max(len(v) for _, v in group)
                path = [sheet.title, f"Table {number}"]
                if len(group) > 1 and sum(bool(v) for v in group[0][1]) == 1 and width > 1:
                    title = next(v for v in group[0][1] if v)
                    blocks.append(
                        ParsedBlock(
                            title,
                            source_name,
                            len(blocks),
                            type="heading",
                            heading_path=(sheet.title, title),
                            metadata={"format": "xlsx", "sheet": sheet.title},
                        )
                    )
                    path = [sheet.title, title, f"Table {number}"]
                    group = group[1:]
                if not group:
                    continue
                header_number, header = group[0]
                inferred = any(re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", v) for v in header)
                data = group if inferred else group[1:]
                if inferred:
                    header = [f"Column {i + 1}" for i in range(width)]
                header = header + [f"Column {i + 1}" for i in range(len(header), width)]

                def render(values, width=width):
                    return "| " + " | ".join(values + [""] * (width - len(values))) + " |"

                head = render(header)
                text = "\n".join([head, render(["---"] * width), *[render(v) for _, v in data]])
                blocks.append(
                    ParsedBlock(
                        text,
                        source_name,
                        len(blocks),
                        heading=" / ".join(path),
                        heading_path=tuple(path),
                        type="table",
                        metadata={
                            "format": "xlsx",
                            "sheet": sheet.title,
                            "table_index": number,
                            "row_start": group[0][0],
                            "row_end": group[-1][0],
                            "row_numbers": [n for n, _ in data],
                            "header_row": None if inferred else header_number,
                            "header": head,
                            "header_inferred": inferred,
                            "quality_warnings": ["FORMULA_WITHOUT_CACHED_VALUE"] if missing else [],
                            "formula_cells_without_cache": missing,
                        },
                    )
                )
        if not blocks:
            raise EmptyExtractedTextError(
                "Workbook contains no cached values; recalculate formulas before upload."
            )
        return blocks
    finally:
        for book in books:
            book.close()
