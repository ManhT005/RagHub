import hashlib
from pathlib import Path

import pytest
from raghub_core.domain.evaluation.metrics import fact_support_scores

from scripts.calibrate_relevance import calibration_rows
from scripts.generate_golden_draft import generate
from scripts.score_fact_support import score_report


def test_valid_citation_id_does_not_imply_fact_support():
    scores = fact_support_scores(
        expected_facts=[{"fact": "cost", "supporting_chunk_ids": ["pricing"]}],
        observed_facts=[{"fact": "cost", "cited_chunk_ids": ["unrelated"]}],
        inventory_chunk_ids={"pricing", "unrelated"},
    )
    assert scores == {"citation_support_precision": 0, "fact_support_recall": 0}
    assert (
        fact_support_scores(expected_facts=[], observed_facts=[], inventory_chunk_ids=set())[
            "citation_support_precision"
        ]
        is None
    )


def test_support_review_is_bound_to_the_exact_answer_and_inventory():
    answer = "Cost is 100 [C1]."
    report = {
        "summary": {},
        "cases": [
            {
                "id": "a",
                "answerable": True,
                "answer": answer,
                "citation_inventory": [{"chunk_id": "pricing"}],
            }
        ],
    }
    annotation = {
        "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
        "expected_facts": [{"fact": "cost", "supporting_chunk_ids": ["pricing"]}],
        "observed_facts": [
            {
                "fact": "cost",
                "claim_text": "Cost is 100 [C1].",
                "cited_chunk_ids": ["pricing"],
            }
        ],
    }
    assert score_report(report, {"a": annotation})["summary"]["fact_support_recall"] == 1
    annotation["answer_sha256"] = "stale"
    report["release_gate"] = {"passed": True}
    assert score_report(report, {"a": annotation})["summary"]["fact_support_recall"] is None
    assert "support_metrics" not in report["cases"][0]
    assert "release_gate" not in report
    annotation["answer_sha256"] = hashlib.sha256(answer.encode()).hexdigest()
    annotation["observed_facts"][0]["claim_text"] = "Invented claim"
    with pytest.raises(ValueError, match="claim text"):
        score_report(report, {"a": annotation})


def test_draft_families_preserve_reference_facts_and_do_not_cross_splits():
    import json

    cases = json.loads(
        (Path(__file__).parent / "fixtures/rag_golden/qa.json").read_text(encoding="utf-8")
    )
    draft = generate(cases)
    assert len(draft) == 210 and all(c["review_status"] == "draft" for c in draft)
    originals = {c["id"]: c for c in cases}
    for case in draft:
        source = originals[case["origin_case_id"]]
        assert case["split"] == source["split"]
        assert case["reference_facts"] == source["reference_facts"]
        assert case["expected_chunk_ids"] == source["expected_chunk_ids"]


def test_calibration_collector_output_excludes_holdout():
    train = [{"fused_scores": [0.1], "answerable": True}]
    holdout = [{"fused_scores": [999], "answerable": False}]
    assert calibration_rows({"calibration": train, "holdout": holdout}) == train
    with pytest.raises(ValueError, match="holdout"):
        calibration_rows([{**holdout[0], "split": "holdout"}])


def test_review_cli_preserves_prior_thresholds_and_fails_missing_evidence(tmp_path, monkeypatch):
    import json

    from scripts.score_fact_support import main

    report_path, annotations_path, out_path = [
        tmp_path / name for name in ("in.json", "review.json", "out.json")
    ]
    report_path.write_text(
        json.dumps(
            {
                "cases": [{"id": "a", "answerable": True, "answer": "An unreviewed answer."}],
                "summary": {"mrr@5": 0.8},
                "release_gate": {"passed": True, "checks": {"mrr@5": {"threshold": 0.95}}},
            }
        ),
        encoding="utf-8",
    )
    annotations_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "score_fact_support",
            "--report",
            str(report_path),
            "--annotations",
            str(annotations_path),
            "--out",
            str(out_path),
            "--gate",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    output = json.loads(out_path.read_text(encoding="utf-8"))
    assert not output["release_gate"]["passed"]
    assert output["release_gate"]["checks"]["mrr@5"]["threshold"] == 0.95
    assert output["summary"]["citation_support_precision"] is None
