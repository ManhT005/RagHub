"""Phase 1: golden dataset contract + metric unit tests (deterministic, offline).

No network, no paid provider, no ES. Fails (red) if fixtures drift.
"""
import hashlib
import json
from pathlib import Path

from raghub_core.domain.evaluation.metrics import (
    citation_coverage,
    citation_precision,
    hit_at_k,
    mrr_at_k,
    ndcg_at_k,
    rejection_scores,
)

GOLDEN = Path(__file__).parent / "fixtures" / "rag_golden"


def _load_qa():
    return json.loads((GOLDEN / "qa.json").read_text(encoding="utf-8"))


def _load_manifest():
    return json.loads((GOLDEN / "corpus_manifest.json").read_text(encoding="utf-8"))


def test_golden_has_30_qa_with_required_distribution():
    qa = _load_qa()
    assert len(qa) == 30
    answerable = [q for q in qa if q["answerable"]]
    unanswerable = [
        q
        for q in qa
        if not q["answerable"] and "ambiguous" not in q["tags"] and "adversarial" not in q["tags"]
    ]
    ambiguous = [q for q in qa if "ambiguous" in q["tags"]]
    adversarial = [q for q in qa if "adversarial" in q["tags"] or "prompt-injection" in q["tags"]]
    assert len(answerable) == 16
    assert len(unanswerable) == 6
    assert len(ambiguous) == 4
    assert len(adversarial) == 4


def test_golden_split_is_fixed_20_calibration_10_holdout():
    qa = _load_qa()
    cal = [q for q in qa if q["split"] == "calibration"]
    hold = [q for q in qa if q["split"] == "holdout"]
    assert len(cal) == 20
    assert len(hold) == 10


def test_golden_has_year_discrimination_and_injection_cases():
    qa = _load_qa()
    assert any("year-discrimination" in q["tags"] for q in qa)
    assert any("prompt-injection" in q["tags"] for q in qa)
    assert any(
        "2025" in " ".join(q.get("reference_facts", []))
        or "doc-008" in str(q.get("expected_document_ids", []))
        for q in qa
    )


def test_golden_qa_schema():
    required = {"id", "corpus_revision", "language", "question", "answerable",
                "expected_document_ids", "expected_chunk_ids", "reference_facts",
                "forbidden_claims", "tags", "split"}
    for q in _load_qa():
        assert required <= set(q), q.get("id")
        assert q["language"] == "vi"
        assert q["corpus_revision"] == "golden-v1"


def test_corpus_manifest_hashes_match_files():
    manifest = _load_manifest()
    assert manifest["corpus_revision"] == "golden-v1"
    assert len(manifest["documents"]) == 9
    for doc in manifest["documents"]:
        for field in ("source_url", "title", "published_at", "retrieved_at",
                      "admission_year", "content_sha256", "source_file"):
            assert field in doc, doc.get("document_id")
        data = (GOLDEN / doc["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == doc["content_sha256"]
    years = {d["admission_year"] for d in manifest["documents"]}
    assert years == {"2026"}


def test_no_category_page_live_dependency():
    manifest = _load_manifest()
    for doc in manifest["documents"]:
        assert "tuyensinh.haui.edu.vn" in doc["source_url"]
        assert (GOLDEN / doc["file"]).exists()


# ---- metric unit tests (red-tests for Phase 1 gate) ----

def test_hit_mrr_ndcg_at_5():
    retrieved = ["a", "b", "c", "d", "e", "f"]
    assert hit_at_k(retrieved, {"c"}) == 1.0
    assert hit_at_k(retrieved, {"z"}) == 0.0
    assert hit_at_k(retrieved, {"f"}, k=5) == 0.0
    assert mrr_at_k(retrieved, {"c"}) == 1 / 3
    assert mrr_at_k(retrieved, {"z"}) == 0.0
    assert ndcg_at_k(["a", "b"], {"a": 3.0, "b": 1.0}) == 1.0
    assert ndcg_at_k(["b", "a"], {"a": 3.0, "b": 1.0}) < 1.0
    assert ndcg_at_k(["z"], {"a": 1.0}) == 0.0


def test_rejection_f1():
    scores = rejection_scores(
        predicted_unanswerable=[True, True, False, False],
        actual_unanswerable=[True, False, True, False],
    )
    assert scores["precision"] == 0.5
    assert scores["recall"] == 0.5
    assert scores["f1"] == 0.5


def test_citation_precision_and_coverage():
    assert citation_precision(cited_ids=["C1"], inventory_ids={"C1"}, supporting_ids={"C1"}) == 1.0
    assert citation_precision(cited_ids=["C99"], inventory_ids={"C1"}, supporting_ids={"C1"}) == 0.0
    assert citation_precision(cited_ids=[], inventory_ids=set(), supporting_ids=set()) == 1.0
    assert citation_coverage(supported_claims=9, total_claims=10) == 0.9


def test_empty_context_fallback_produces_no_citation():
    from raghub_core.domain.retrieval.hybrid import build_context_bundle
    bundle = build_context_bundle([], max_tokens=6000)
    assert bundle.text == ""
    assert bundle.hits == []
