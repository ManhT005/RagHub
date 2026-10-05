from uuid import NAMESPACE_DNS, uuid5

from app.infrastructure.elasticsearch.chunks import chunk_index_mapping
from app.modules.ingestion.tokenizer import ENCODING
from app.modules.search.hybrid import build_context, build_context_bundle, fuse_rrf


def identifier(name):
    return str(uuid5(NAMESPACE_DNS, name))


def hit(chunk_id: str, content: str = "content") -> dict[str, object]:
    return {
        "chunk_id": identifier(chunk_id),
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

    assert [item["chunk_id"] for item in fused] == [
        identifier(x) for x in ("shared", "lexical", "vector")
    ]
    assert fused[0]["score"] == 1 / 62 + 1 / 61


def test_context_keeps_chunk_citation_and_honors_token_budget() -> None:
    context = build_context([hit("citation-id", "word " * 200)], max_tokens=70)

    assert f"chunk_id: {identifier('citation-id')}" in context
    assert len(ENCODING.encode(context)) <= 70


def test_context_bundle_contains_only_used_hits() -> None:
    hits = [hit("first"), hit("second"), hit("unused")]
    first_two_tokens = len(ENCODING.encode(build_context_bundle(hits[:2], max_tokens=10_000).text))

    bundle = build_context_bundle(hits, max_tokens=first_two_tokens)

    assert [item["chunk_id"] for item in bundle.hits] == [identifier("first"), identifier("second")]
    assert "[C1]" in bundle.text
    assert "[C2]" in bundle.text
    assert "unused" not in bundle.text


def test_context_bundle_keeps_chunk_metadata() -> None:
    original = hit("metadata")

    bundle = build_context_bundle([original])

    assert bundle.hits == [original]
    assert bundle.hits[0]["document_version_id"] == original["document_version_id"]


def test_index_mapping_matches_embedding_dimension() -> None:
    mapping = chunk_index_mapping(768)

    assert mapping["mappings"]["properties"]["embedding"]["dims"] == 768
