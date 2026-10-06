"""Attach reviewer-verified claim/source metrics to an immutable production report."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from raghub_core.domain.evaluation.metrics import fact_support_scores  # noqa: E402

from scripts.run_production_eval import (  # noqa: E402
    DEFAULT_GATE_THRESHOLDS,
    evaluate_release_gate,
)


def score_report(report, annotations):
    # A verdict on the previous metrics cannot survive a new review.
    report.pop("release_gate", None)
    missing = []
    reviewed = [c for c in report["cases"] if not c.get("provider_error")]
    eligible = [c for c in reviewed if c["answerable"]]
    for case in reviewed:
        case.pop("support_metrics", None)
        review = annotations.get(case["id"])
        digest = hashlib.sha256(case["answer"].encode()).hexdigest()
        if not review or review.get("answer_sha256") != digest:
            missing.append(case["id"])
            continue
        inventory = {str(c["chunk_id"]) for c in case.get("citation_inventory", [])}
        for claim in review.get("observed_facts", []):
            if not claim.get("claim_text") or claim["claim_text"] not in case["answer"]:
                raise ValueError("Reviewed claim text must match the recorded answer.")
        case["support_metrics"] = fact_support_scores(
            expected_facts=review.get("expected_facts", []),
            observed_facts=review.get("observed_facts", []),
            inventory_chunk_ids=inventory,
        )
    metrics = ["citation_support_precision", "fact_support_recall", "unsupported_claim_rate"]
    for metric in metrics:
        metric_cases = reviewed if metric == "unsupported_claim_rate" else eligible
        values = [c.get("support_metrics", {}).get(metric) for c in metric_cases]
        report["summary"][metric] = (
            sum(values) / len(values)
            if values and not missing and all(v is not None for v in values)
            else None
        )
    report["support_review"] = {
        "eligible_cases": len(reviewed),
        "answerable_cases": len(eligible),
        "missing_or_stale": missing,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--require-reviewed-v2", action="store_true")
    parser.add_argument("--thresholds", type=Path, help="JSON metric/threshold overrides")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    previous_thresholds = {
        metric: check["threshold"]
        for metric, check in report.get("release_gate", {}).get("checks", {}).items()
    }
    thresholds = {
        **DEFAULT_GATE_THRESHOLDS,
        "citation_support_precision": 0.90,
        "fact_support_recall": 0.85,
        "unsupported_claim_rate": 0.10,
        **previous_thresholds,
    }
    if args.thresholds:
        thresholds.update(json.loads(args.thresholds.read_text(encoding="utf-8")))
    if args.require_reviewed_v2:
        thresholds["dataset_release_eligible"] = True
    report = score_report(report, json.loads(args.annotations.read_text(encoding="utf-8")))
    passed, checks = evaluate_release_gate(report["summary"], thresholds)
    report["release_gate"] = {"enabled": args.gate, "passed": passed, "checks": checks}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["support_review"]))
    if report["summary"]["citation_support_precision"] is None or (args.gate and not passed):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
