"""Calibrate the relevance gate on the golden calibration split.

Input: scores JSON list of {"fused_scores": [...], "answerable": bool}.
Output: artifact JSON with dataset/retrieval-config hashes, logistic
weights fit by batch gradient descent (pure stdlib) and the F1-maximizing
threshold on the training split. The holdout split is never used here;
evaluate it separately with scripts/rag_golden_eval.py.

Usage (from backend/):
    python scripts/calibrate_relevance.py --scores scores.json --out artifact.json \\
        --dataset-hash <qa-hash> --config-hash <retrieval-hash> --version baseline-v1
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from raghub_core.domain.evaluation.metrics import rejection_scores  # noqa: E402
from raghub_core.domain.retrieval.relevance import (  # noqa: E402
    default_features,
    extract_features,
    sigmoid,
)


def _design(rows: list[dict], names: tuple[str, ...]) -> tuple[list[list[float]], list[int]]:
    matrix, labels = [], []
    for row in rows:
        features = extract_features(row["fused_scores"], feature_names=names)
        matrix.append([features[name] for name in names])
        labels.append(1 if row["answerable"] else 0)
    return matrix, labels


def calibration_rows(payload) -> list[dict]:
    """Accept collector output without mixing holdout observations into training."""
    rows = payload.get("calibration") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or any(
        row.get("split", "calibration") != "calibration" for row in rows
    ):
        raise ValueError("Expected calibration rows only; holdout must be evaluated separately.")
    return rows


def fit_logistic(
    matrix: list[list[float]], labels: list[int], *, steps: int = 2000, rate: float = 0.1
) -> tuple[list[float], float]:
    dim = len(matrix[0])
    weights = [0.0] * dim
    intercept = 0.0
    for _ in range(steps):
        grad_w = [0.0] * dim
        grad_b = 0.0
        for row, label in zip(matrix, labels, strict=False):
            pred = sigmoid(sum(w * x for w, x in zip(weights, row, strict=False)) + intercept)
            err = pred - label
            for j in range(dim):
                grad_w[j] += err * row[j]
            grad_b += err
        scale = rate / len(matrix)
        weights = [w - scale * g for w, g in zip(weights, grad_w, strict=False)]
        intercept -= scale * grad_b
    return weights, intercept


def best_threshold(scores: list[float], labels: list[int]) -> tuple[float, float]:
    points = sorted(set(scores))
    candidates = list(points)
    candidates += [(a + b) / 2 for a, b in zip(points, points[1:], strict=False)]
    best, best_f1 = 0.5, -1.0
    for candidate in candidates:
        predicted = [s < candidate for s in scores]  # low P(answerable) -> unanswerable
        actual = [label == 0 for label in labels]  # True when unanswerable
        f1 = rejection_scores(predicted_unanswerable=predicted, actual_unanswerable=actual)["f1"]
        if f1 > best_f1:
            best, best_f1 = candidate, f1
    return best, best_f1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dataset-hash", required=True)
    parser.add_argument("--config-hash", required=True)
    parser.add_argument("--version", default="baseline-v1")
    parser.add_argument("--fingerprint", required=True)
    args = parser.parse_args()

    rows = calibration_rows(json.loads(Path(args.scores).read_text(encoding="utf-8")))
    names = default_features()
    matrix, labels = _design(rows, names)
    if not matrix or len(set(labels)) != 2:
        raise ValueError("Calibration requires positive and negative training examples.")
    means = [sum(row[j] for row in matrix) / len(matrix) for j in range(len(names))]
    stds = [
        max(math.sqrt(sum((row[j] - means[j]) ** 2 for row in matrix) / len(matrix)), 1e-8)
        for j in range(len(names))
    ]
    matrix = [[(x - means[j]) / stds[j] for j, x in enumerate(row)] for row in matrix]
    weights, intercept = fit_logistic(matrix, labels)
    probs = [
        sigmoid(sum(w * x for w, x in zip(weights, row, strict=False)) + intercept)
        for row in matrix
    ]
    threshold, train_f1 = best_threshold(probs, labels)
    artifact = {
        "version": args.version,
        "feature_names": list(names),
        "weights": weights,
        "feature_mean": means,
        "feature_std": stds,
        "intercept": intercept,
        "threshold": threshold,
        "train_rejection_f1": train_f1,
        "dataset_hash": args.dataset_hash,
        "retrieval_config_hash": args.config_hash,
        "embedding_fingerprint": args.fingerprint,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps({"threshold": threshold, "train_rejection_f1": train_f1}))


if __name__ == "__main__":
    main()
