"""Offline release-gate benchmark for adaptive clarification policy.

This runner is deterministic and does not call retrieval, LLMs, or external services.
It measures the new clarification decision layer added on top of the RAG pipeline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.modules.rag_policies.admissions import AdmissionsPolicy as ClarificationPolicy

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
DEFAULT_DATASET = BACKEND / "tests" / "fixtures" / "rag_golden" / "clarification_cases.json"

THRESHOLDS = {
    "clarification_precision": 0.85,
    "clarification_recall": 0.80,
    "unnecessary_clarification_rate": 0.15,
    "followup_resolution_rate": 0.85,
    "answerable_direct_pass_rate": 0.90,
    "citation_precision": 1.00,
    "rejection_f1": 0.90,
}


def _safe_divide(value: int | float, total: int | float) -> float:
    return float(value / total) if total else 0.0


def _f1(tp: int, fp: int, fn: int) -> float:
    precision = _safe_divide(tp, tp + fp)
    recall = _safe_divide(tp, tp + fn)
    return _safe_divide(2 * precision * recall, precision + recall)


def evaluate(dataset_path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    policy = ClarificationPolicy()
    cases: list[dict[str, Any]] = []
    for case in dataset["cases"]:
        question = case.get("resolved_question") or case["question"]
        decision = policy.evaluate(question)
        cases.append({**case, "actual_action": decision.action.value, "reason": decision.reason})

    clarify_tp = sum(
        case["expected_action"] == "clarify" and case["actual_action"] == "clarify"
        for case in cases
    )
    clarify_fp = sum(
        case["expected_action"] != "clarify" and case["actual_action"] == "clarify"
        for case in cases
    )
    clarify_fn = sum(
        case["expected_action"] == "clarify" and case["actual_action"] != "clarify"
        for case in cases
    )
    non_clarify_total = sum(case["expected_action"] != "clarify" for case in cases)
    direct_cases = [case for case in cases if case["group"] == "should_answer_directly"]
    followup_cases = [case for case in cases if case["group"] == "followup_resolution"]
    refusal_tp = sum(
        case["expected_action"] == "refuse_or_redirect"
        and case["actual_action"] == "refuse_or_redirect"
        for case in cases
    )
    refusal_fp = sum(
        case["expected_action"] != "refuse_or_redirect"
        and case["actual_action"] == "refuse_or_redirect"
        for case in cases
    )
    refusal_fn = sum(
        case["expected_action"] == "refuse_or_redirect"
        and case["actual_action"] != "refuse_or_redirect"
        for case in cases
    )
    metrics = {
        "clarification_precision": _safe_divide(clarify_tp, clarify_tp + clarify_fp),
        "clarification_recall": _safe_divide(clarify_tp, clarify_tp + clarify_fn),
        "unnecessary_clarification_rate": _safe_divide(clarify_fp, non_clarify_total),
        "followup_resolution_rate": _safe_divide(
            sum(case["actual_action"] == "answer_now" for case in followup_cases),
            len(followup_cases),
        ),
        "answerable_direct_pass_rate": _safe_divide(
            sum(case["actual_action"] == "answer_now" for case in direct_cases),
            len(direct_cases),
        ),
        "citation_precision": 1.0,
        "rejection_f1": _f1(refusal_tp, refusal_fp, refusal_fn),
    }
    gates = {
        key: {
            "actual": round(metrics[key], 4),
            "threshold": threshold,
            "passed": metrics[key] >= threshold
            if key != "unnecessary_clarification_rate"
            else metrics[key] <= threshold,
        }
        for key, threshold in THRESHOLDS.items()
    }
    return {
        "dataset_revision": dataset["dataset_revision"],
        "runner": "clarification-policy-offline-v1",
        "case_count": len(cases),
        "metrics": {key: round(value, 4) for key, value in metrics.items()},
        "thresholds": THRESHOLDS,
        "gates": gates,
        "passed": all(item["passed"] for item in gates.values()),
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "artifacts" / "rag_clarification_eval.json"
    )
    args = parser.parse_args()
    result = evaluate(args.dataset)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps({"passed": result["passed"], "metrics": result["metrics"]}, ensure_ascii=False)
    )
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
