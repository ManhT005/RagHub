from app.infrastructure.elasticsearch.chunks import chunk_index_mapping
from app.modules.ingestion.tokenizer import ENCODING
from app.modules.search.hybrid import build_context, fuse_rrf


def hit(chunk_id: str, content: str = "content") -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": "00000000-0000-0000-0000-000000000001",
        "document_version_id": "00000000-0000-0000-0000-000000000002",
        "content": content,
        "source_name": "guide.md",
        "page_number": 2,
        "heading": "Hybrid search",
        "score": 1.0,
    }


def test_rrf_prefers_a_chunk_returned_by_both_retrievers() -> None:
    fused = fuse_rrf([[hit("lexical"), hit("shared")], [hit("shared"), hit("vector")]], limit=5)

    assert [item["chunk_id"] for item in fused] == ["shared", "lexical", "vector"]
    assert fused[0]["score"] == 1 / 62 + 1 / 61


def test_context_keeps_chunk_citation_and_honors_token_budget() -> None:
    context = build_context([hit("citation-id", "word " * 200)], max_tokens=30)

    assert "chunk_id=citation-id" in context
    assert len(ENCODING.encode(context)) <= 30


def test_index_mapping_matches_embedding_dimension() -> None:
    mapping = chunk_index_mapping(768)

    assert mapping["mappings"]["properties"]["embedding"]["dims"] == 768
