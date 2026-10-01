from app.modules.chatbots.citations import resolve_citations
from app.modules.search.hybrid import build_context_bundle


def hit(chunk_id: str, content: str = "content") -> dict[str, object]:
    return {
        "document_id": "00000000-0000-0000-0000-000000000001",
        "document_version_id": "00000000-0000-0000-0000-000000000002",
        "chunk_id": chunk_id,
        "source_name": "guide.pdf",
        "page_number": 3,
        "content": content,
        "score": 0.032,
    }


def test_citations_are_resolved_only_from_context_bundle_hits() -> None:
    candidates = [hit("used"), hit("excluded", "word " * 500)]
    budget = len(build_context_bundle(candidates[:1]).text)
    bundle = build_context_bundle(candidates, max_tokens=budget)

    citations = resolve_citations(bundle.hits)

    assert [citation["citation_id"] for citation in citations] == ["C1"]
    assert [citation["chunk_id"] for citation in citations] == ["used"]


def test_citation_metadata_comes_from_backend_hit() -> None:
    citations = resolve_citations([hit("trusted")])

    assert citations == [
        {
            "citation_id": "C1",
            "document_id": "00000000-0000-0000-0000-000000000001",
            "document_name": "guide.pdf",
            "page": 3,
            "chunk_id": "trusted",
            "excerpt": "content",
            "score": 0.032,
        }
    ]


def test_model_text_cannot_create_a_backend_citation() -> None:
    model_answer = "See [C99] and https://example.com/fake.pdf on page 9."

    citations = resolve_citations([hit("trusted")])

    assert model_answer not in str(citations)
    assert [citation["citation_id"] for citation in citations] == ["C1"]
