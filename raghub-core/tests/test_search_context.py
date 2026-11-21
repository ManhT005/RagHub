from dataclasses import replace
from uuid import uuid4

from raghub_core.domain.ingestion.markdown_v2 import chunk_markdown_blocks, parse_markdown_blocks
from raghub_core.domain.retrieval.context import rerank_text, search_context
from raghub_core.domain.retrieval.models import RetrievedChunk


def chunk(content="Body", source="Report_2026.md", **kwargs):
    return RetrievedChunk(uuid4(), uuid4(), uuid4(), content, source, None, None, 1, **kwargs)


def test_filename_is_searchable_but_never_promoted_to_fact_year():
    c = search_context(chunk())
    assert c["source_title"] == "Report 2026"
    assert c["document_years"] == [2026]
    assert c["fact_years"] == []
    assert search_context(chunk("Quyết định ban hành ngày 01/01/2020"))["fact_years"] == []


def test_nearest_section_and_local_caption_override_filename_and_parent_year():
    c = chunk(heading_path=("Thông tin 2026", "Điểm chuẩn năm 2025"))
    ctx = search_context(c)
    assert ctx["fact_years"] == [2025]
    assert ctx["context_conflicts"] == ["source_context_year_mismatch"]
    assert search_context(replace(c, metadata={"table_title": "Bảng học phí 2024"}))[
        "fact_years"
    ] == [2024]


def test_historical_table_retains_multiple_column_years_and_exact_entity_codes():
    c = chunk(
        "| Mã ngành | Ngành | 2024 | 2025 |\n"
        "| --- | --- | --- | --- |\n| 7480201 | CNTT | 25 | 23,09 |",
        heading_path=("Thông tin tuyển sinh năm 2026",),
    )
    ctx = search_context(c)
    assert ctx["fact_years"] == [2024, 2025]
    assert ctx["entity_codes"] == ["7480201"]
    assert ctx["year_evidence"] == "table_headers"


def test_context_applies_to_product_codes_and_english_documents():
    c = chunk(
        "| Product code | Price |\n| --- | --- |\n| AB-12345 | 300 |",
        source="price_list_2025.xlsx",
        metadata={"table_title": "Prices 2024"},
    )
    ctx = search_context(c)
    assert ctx["fact_years"] == [2024]
    assert ctx["entity_codes"] == ["AB-12345"]
    assert "Columns: Product code | Price" in rerank_text(c)
    assert "Content:" in rerank_text(c)
    assert c.content in rerank_text(c)


def test_long_table_carries_caption_headers_and_complete_rows_into_every_chunk():
    rows = [f"| {7000000 + i} | Chương trình {i} | 23,09 |" for i in range(30)]
    text = (
        "# Tuyển sinh 2026\n\n1. Điểm chuẩn năm 2025:\n\n"
        "| Mã ngành | Ngành | Điểm |\n| --- | --- | --- |\n" + "\n".join(rows)
    )
    chunks = chunk_markdown_blocks(
        parse_markdown_blocks(text.encode(), "wrong_2026.md"), uuid4(), target_tokens=220
    )
    tables = [c for c in chunks if c.metadata["block_type"] == "table"]
    assert len(tables) > 2
    for c in tables:
        ctx = c.metadata["search_context"]
        assert ctx["fact_years"] == [2025]
        assert ctx["table_title"] == "1. Điểm chuẩn năm 2025:"
        assert ctx["table_headers"] == ["Mã ngành", "Ngành", "Điểm"]
        assert c.content.startswith("| Mã ngành | Ngành | Điểm |")
    for row in rows:
        assert sum(row in c.content.splitlines() for c in tables) == 1


def test_query_matching_row_is_visible_before_long_table_body_to_reranker():
    rows = [f"| {i} | Other programme {i} | 20 |" for i in range(50)]
    answer = "| 7480201 | Công nghệ thông tin | 23,09 |"
    c = chunk(
        "| Code | Programme | Score |\n| --- | --- | --- |\n" + "\n".join([*rows, answer]),
        heading_path=("Điểm chuẩn 2025",),
    )
    text = rerank_text(c, "điểm chuẩn công nghệ thông tin 2025 là bao nhiêu")
    assert text.index(answer) < text.index("Content:")
    assert c.content in text


def test_caption_is_not_inherited_across_pages_or_sections():
    from raghub_core.domain.ingestion.parser import ParsedBlock

    caption = ParsedBlock(
        "1. Prices 2024:",
        "a.pdf",
        0,
        page_number=1,
        type="paragraph",
        heading_path=("Overview 2026",),
    )
    table = ParsedBlock(
        "| Code | Price |\n| --- | --- |\n| A12345 | 30 |",
        "a.pdf",
        1,
        page_number=2,
        type="table",
        heading_path=("Overview 2026",),
    )
    chunks = chunk_markdown_blocks([caption, table], uuid4(), pipeline="document-v2")
    assert "table_title" not in chunks[-1].metadata
    assert chunks[-1].metadata["search_context"]["fact_years"] == [2026]
    table = replace(table, page_number=1, heading_path=("Other 2023",))
    chunks = chunk_markdown_blocks([caption, table], uuid4(), pipeline="document-v2")
    assert chunks[-1].metadata["search_context"]["fact_years"] == [2023]


def test_rerank_context_does_not_modify_chunk_identity_body_or_citation():
    c = chunk("Original  text", source="incorrect_2026.md", heading_path=("Overview 2025",))
    before = replace(c)
    formatted = rerank_text(c, "overview 2025")
    assert "Overview 2025" in formatted and "incorrect 2026" in formatted
    assert c == before


def test_generation_context_retains_local_table_caption_that_disagrees_with_filename():
    from raghub_core.domain.retrieval.hybrid import build_context_bundle

    c = chunk(
        "| CNTT | 23,09 |", source="wrong_2026.md", metadata={"table_title": "Điểm chuẩn năm 2025"}
    )
    bundle = build_context_bundle([c])
    assert "source: wrong_2026.md" in bundle.text
    assert "table_title: Điểm chuẩn năm 2025" in bundle.text
    assert c.content in bundle.text
    assert bundle.hits == [c]


def test_long_parent_headings_do_not_hide_relevant_row_behind_metadata():
    c = chunk(
        "| Code | Score |\n| --- | --- |\n| 7480201 | 23,09 |",
        heading_path=("Long parent " * 300, "Điểm chuẩn 2025"),
    )
    text = rerank_text(c, "7480201 2025")
    assert text.index("7480201 | 23,09") < 600
    assert "Điểm chuẩn 2025" in text[:300]
