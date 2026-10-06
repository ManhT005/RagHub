from pathlib import Path

from scripts.evaluate_clarification_policy import evaluate


def test_clarification_policy_eval_release_gates_pass() -> None:
    result = evaluate(Path("tests/fixtures/rag_golden/clarification_cases.json"))

    assert result["passed"] is True
    assert result["case_count"] >= 20
    assert result["metrics"]["citation_precision"] == 1.0
    assert set(result["gates"]) == {
        "clarification_precision",
        "clarification_recall",
        "unnecessary_clarification_rate",
        "followup_resolution_rate",
        "answerable_direct_pass_rate",
        "citation_precision",
        "rejection_f1",
    }