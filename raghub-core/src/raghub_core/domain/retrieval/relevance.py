"""Calibrated relevance gate: ACCEPT or REJECT a fused candidate list.

Confidence is a logistic function of stable cross-query features, never a
raw BM25/RRF threshold. The gate only engages when the artifact version and
its dataset/retrieval-config hashes match the running setup; any mismatch
keeps the gate off (legacy top-k behavior) instead of mis-rejecting.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RelevanceArtifact:
    version: str
    feature_names: tuple[str, ...]
    weights: tuple[float, ...]
    intercept: float
    threshold: float
    dataset_hash: str
    retrieval_config_hash: str
    embedding_fingerprint: str
    feature_mean: tuple[float, ...] = ()
    feature_std: tuple[float, ...] = ()


@dataclass(frozen=True)
class RelevanceDecision:
    accepted: bool
    confidence: float


def sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    clipped = math.exp(value)
    return clipped / (1.0 + clipped)


def extract_features(
    fused_scores: list[float],
    *,
    feature_names: tuple[str, ...] = ("fused_1", "margin_12", "mean_top3", "n_results"),
    limit: int = 5,
) -> dict[str, float]:
    """Stable features from one fused ranking (query-independent scale)."""
    top = fused_scores[:limit]
    first = top[0] if top else 0.0
    second = top[1] if len(top) > 1 else 0.0
    features = {
        "fused_1": first,
        "margin_12": first - second,
        "mean_top3": sum(top[:3]) / min(3, len(top)) if top else 0.0,
        "n_results": float(len(fused_scores)),
    }
    return {name: features[name] for name in feature_names if name in features}


def score_candidates(artifact: RelevanceArtifact, fused_scores: list[float]) -> float:
    features = extract_features(fused_scores, feature_names=artifact.feature_names)
    if artifact.feature_mean and artifact.feature_std:
        features = {
            name: (features[name] - mean) / std
            for name, mean, std in zip(
                artifact.feature_names, artifact.feature_mean, artifact.feature_std, strict=True
            )
        }
    linear = artifact.intercept + sum(
        weight * features.get(name, 0.0)
        for weight, name in zip(artifact.weights, artifact.feature_names, strict=False)
    )
    return sigmoid(linear)


def gate_enabled(
    artifact: RelevanceArtifact | None,
    *,
    enabled_flag: bool,
    dataset_hash: str,
    retrieval_config_hash: str,
    embedding_fingerprint: str = "",
) -> bool:
    """The gate engages only on flag + versioned artifact + matching hashes."""
    if not enabled_flag or artifact is None:
        return False
    return (
        bool(embedding_fingerprint)
        and artifact.embedding_fingerprint == embedding_fingerprint
        and artifact.dataset_hash == dataset_hash
        and artifact.retrieval_config_hash == retrieval_config_hash
    )


def decide(
    artifact: RelevanceArtifact,
    fused_scores: list[float],
    *,
    enabled_flag: bool,
    dataset_hash: str,
    retrieval_config_hash: str,
    embedding_fingerprint: str = "",
) -> RelevanceDecision:
    if not gate_enabled(
        artifact,
        enabled_flag=enabled_flag,
        dataset_hash=dataset_hash,
        retrieval_config_hash=retrieval_config_hash,
        embedding_fingerprint=embedding_fingerprint,
    ):
        return RelevanceDecision(accepted=True, confidence=1.0)
    if not fused_scores:
        return RelevanceDecision(accepted=False, confidence=0.0)
    if not 0.0 < artifact.threshold < 1.0:
        # Uncalibrated artifact (e.g. unreachable threshold): never reject.
        return RelevanceDecision(accepted=True, confidence=1.0)
    confidence = score_candidates(artifact, fused_scores)
    return RelevanceDecision(accepted=confidence >= artifact.threshold, confidence=confidence)


def default_features() -> tuple[str, ...]:
    return ("fused_1", "margin_12", "mean_top3", "n_results")


def empty_artifact(version: str) -> RelevanceArtifact:
    return RelevanceArtifact(
        version=version,
        feature_names=default_features(),
        weights=(0.0,) * len(default_features()),
        intercept=0.0,
        threshold=1.01,  # unreachable: never rejects until calibrated
        dataset_hash="",
        retrieval_config_hash="",
        embedding_fingerprint="",
    )
