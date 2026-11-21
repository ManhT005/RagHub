"""Real ES ranking checks; run against a disposable server, never a workspace index."""

import os
from uuid import uuid4

import pytest
from elasticsearch import Elasticsearch
from raghub_core.domain.ingestion.markdown_v2 import chunk_markdown_blocks, parse_markdown_blocks

from app.infrastructure.elasticsearch.chunks import bm25_query, chunk_index_mapping

URL = os.environ.get("RAGHUB_CONTEXT_TEST_ES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Requires a disposable context test Elasticsearch")


@pytest.fixture
def index():
    client = Elasticsearch(URL)
    name = "raghub_context_test_" + uuid4().hex
    client.indices.create(index=name, **chunk_index_mapping(2))
    try:
        yield client, name
    finally:
        client.indices.delete(index=name)
        client.close()


def add(client, index, org, ws, name, title, rows, headers):
    from raghub_core.domain.retrieval.context import search_context

    text = (
        f"# {title}\n\n| "
        + " | ".join(headers)
        + " |\n| "
        + " | ".join(["---"] * len(headers))
        + " |\n"
        + "\n".join("| " + " | ".join(row) + " |" for row in rows)
    )
    chunks = chunk_markdown_blocks(parse_markdown_blocks(text.encode(), name), uuid4())
    for chunk in chunks:
        client.index(
            index=index,
            id=str(chunk.chunk_id),
            document={
                "organization_id": str(org),
                "workspace_id": str(ws),
                "retrievable": True,
                "content": chunk.content,
                "heading": chunk.heading,
                "source_name": name,
                **search_context(chunk),
            },
        )


def test_wrong_filename_multiple_years_and_topic_ranking(index):
    client, name = index
    org, ws = uuid4(), uuid4()
    add(
        client,
        name,
        org,
        ws,
        "wrong_2026.md",
        "Điểm chuẩn trúng tuyển năm 2025",
        [["7480201", "Công nghệ thông tin", "23,09"], ["7480103", "Kỹ thuật phần mềm", "21,75"]],
        ["Mã ngành", "Tên ngành", "Điểm chuẩn"],
    )
    add(
        client,
        name,
        org,
        ws,
        "diem_chuan_2025.md",
        "Điểm chuẩn năm 2023",
        [["7480201", "Công nghệ thông tin", "25,22"]],
        ["Mã ngành", "Tên ngành", "Điểm chuẩn"],
    )
    add(
        client,
        name,
        org,
        ws,
        "chi_tieu_2025.md",
        "Chỉ tiêu tuyển sinh năm 2025",
        [["7480201", "Công nghệ thông tin", "300"]],
        ["Mã ngành", "Tên ngành", "Chỉ tiêu"],
    )
    # A better matching document from another tenant must never be returned.
    add(
        client,
        name,
        uuid4(),
        uuid4(),
        "diem_chuan_2025.md",
        "Điểm chuẩn công nghệ thông tin năm 2025",
        [["7480201", "Công nghệ thông tin", "99"]],
        ["Mã ngành", "Tên ngành", "Điểm chuẩn"],
    )
    client.indices.refresh(index=name)
    for query, expected in [
        ("điểm chuẩn công nghệ thông tin 2025", "23,09"),
        ("điểm chuẩn ngành 7480201 2025", "23,09"),
        ("điểm chuẩn công nghệ thông tin 2023", "25,22"),
        ("chỉ tiêu công nghệ thông tin 2025", "300"),
        ("diem chuan cong nghe thong tin 2025", "23,09"),
    ]:
        result = client.search(index=name, query=bm25_query(query, org, ws), size=5)
        hits = result["hits"]["hits"]
        assert expected in hits[0]["_source"]["content"], query
        assert all(h["_source"]["organization_id"] == str(org) for h in hits)


def test_headers_and_product_identifiers_are_searchable(index):
    client, name = index
    org, ws = uuid4(), uuid4()
    add(
        client,
        name,
        org,
        ws,
        "inventory.xlsx",
        "Giá bán năm 2025",
        [["AB-12345", "Bơm nước", "1500000"]],
        ["Product code", "Tên sản phẩm", "Giá bán"],
    )
    add(
        client,
        name,
        org,
        ws,
        "inventory_2025.xlsx",
        "Tồn kho năm 2025",
        [["AB-12345", "Bơm nước", "20"]],
        ["Product code", "Tên sản phẩm", "Tồn kho"],
    )
    client.indices.refresh(index=name)
    result = client.search(index=name, query=bm25_query("giá bán AB-12345 2025", org, ws), size=5)
    assert "1500000" in result["hits"]["hits"][0]["_source"]["content"]
    # The new title field splits underscores; metadata itself remains disabled.
    tokens = client.indices.analyze(
        index=name, field="source_title", text="Thông tin tuyển sinh 2025"
    )
    assert "2025" in [t["token"] for t in tokens["tokens"]]


@pytest.mark.parametrize(
    "query,expected",
    [
        ("học phí cơ khí 2025", "850000"),
        ("cho tôi biết học phí cơ khí năm 2025 là bao nhiêu", "850000"),
        ("hoc phi co khi 2025", "850000"),
        ("học phí cơ khí 2024", "750000"),
        ("học phí 7510201 năm 2025", "850000"),
        ("hạn đăng ký học bổng 2025", "30/09/2025"),
        ("hạn đăng ký học bổng 2024", "15/09/2024"),
        ("hồ sơ học bổng 2025", "Giấy xác nhận thu nhập"),
        ("địa điểm nộp hồ sơ học bổng 2025", "Phòng A105"),
        ("warranty AB-12345 2025", "36 months"),
        ("what is warranty AB-12345 2025", "36 months"),
        ("warranty AB-12345 2024", "24 months"),
        ("giá bán AB-12345 2025", "1500000"),
        ("giá bán AB-12345 2024", "1400000"),
    ],
)
def test_context_search_generalizes_across_fees_procedures_and_products(index, query, expected):
    client, name = index
    org, ws = uuid4(), uuid4()
    for year, fee in [(2024, "750000"), (2025, "850000")]:
        add(
            client,
            name,
            org,
            ws,
            "unnamed.xlsx",
            f"Học phí năm {year}",
            [["7510201", "Cơ khí", fee]],
            ["Mã ngành", "Ngành", "Học phí"],
        )
    for year, date in [(2024, "15/09/2024"), (2025, "30/09/2025")]:
        add(
            client,
            name,
            org,
            ws,
            "huong_dan_2026.md",
            f"Hạn đăng ký học bổng {year}",
            [["Đăng ký học bổng", date]],
            ["Thủ tục", "Hạn đăng ký"],
        )
    add(
        client,
        name,
        org,
        ws,
        "huong_dan_2026.md",
        "Hồ sơ học bổng 2025",
        [["Giấy xác nhận thu nhập"]],
        ["Hồ sơ"],
    )
    add(
        client,
        name,
        org,
        ws,
        "huong_dan_2026.md",
        "Địa điểm nộp hồ sơ học bổng 2025",
        [["Phòng A105"]],
        ["Địa điểm nộp hồ sơ"],
    )
    for year, warranty, price in [(2024, "24 months", "1400000"), (2025, "36 months", "1500000")]:
        add(
            client,
            name,
            org,
            ws,
            "inventory.xlsx",
            f"Warranty {year}",
            [["AB-12345", warranty]],
            ["Product code", "Warranty"],
        )
        add(
            client,
            name,
            org,
            ws,
            "inventory.xlsx",
            f"Giá bán {year}",
            [["AB-12345", price]],
            ["Product code", "Giá bán"],
        )
    client.indices.refresh(index=name)
    result = client.search(index=name, query=bm25_query(query, org, ws), size=5)
    assert expected in result["hits"]["hits"][0]["_source"]["content"], query


def test_legacy_documents_without_context_remain_searchable_and_unpublished_chunks_stay_hidden(
    index,
):
    client, name = index
    org, ws = uuid4(), uuid4()
    doc = {
        "organization_id": str(org),
        "workspace_id": str(ws),
        "retrievable": True,
        "source_name": "old.md",
        "content": "Hướng dẫn đăng ký nhập học năm 2025",
    }
    client.index(index=name, id="legacy", document=doc)
    client.index(
        index=name,
        id="not-ready",
        document={
            **doc,
            "retrievable": False,
            "content": "Hướng dẫn đăng ký nhập học năm 2025 " * 5,
        },
    )
    client.indices.refresh(index=name)
    result = client.search(index=name, query=bm25_query("đăng ký nhập học 2025", org, ws), size=5)
    assert [h["_id"] for h in result["hits"]["hits"]] == ["legacy"]
