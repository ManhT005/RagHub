"""Relevance artifact loading: any problem keeps the gate off."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from raghub_core.domain.retrieval.relevance import RelevanceArtifact


def dataset_hash(qa_path: Path) -> str:
    payload = qa_path.read_bytes()
    return hashlib.sha256(payload).hexdigest()[:16]


def retrieval_config_hash(*, candidates: int, rrf_k: int, mapping_version: str) -> str:
    cfg = {"candidates": candidates, "rrf_k": rrf_k, "mapping_version": mapping_version}
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]


def load_relevance_artifact(path: Path, *, expected_version: str) -> RelevanceArtifact | None:
    """Return the artifact, or None (gate off) on any mismatch/corruption."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        if data.get("version") != expected_version:
            return None
        names = tuple(data["feature_names"])
        weights = tuple(float(w) for w in data["weights"])
        if len(names) == 0 or len(names) != len(weights):
            return None
        threshold = float(data["threshold"])
        if not 0.0 < threshold < 1.0:
            return None
        mean = tuple(float(x) for x in data.get("feature_mean", ()))
        std = tuple(float(x) for x in data.get("feature_std", ()))
        if mean or std:
            if len(mean) != len(names) or len(std) != len(names):
                return None
            if not all(math.isfinite(x) for x in mean + std) or any(x <= 0 for x in std):
                return None
        from raghub_core.domain.retrieval.relevance import default_features
        if len(set(names)) != len(names) or not set(names) <= set(default_features()):
            return None
        if not all(math.isfinite(x) for x in weights + (float(data["intercept"]),)):
            return None
        return RelevanceArtifact(
            version=data["version"],
            feature_mean=mean,
            feature_std=std,
            feature_names=names,
            weights=weights,
            intercept=float(data["intercept"]),
            threshold=threshold,
            dataset_hash=str(data["dataset_hash"]),
            retrieval_config_hash=str(data["retrieval_config_hash"]),
            embedding_fingerprint=str(data.get("embedding_fingerprint", "")),
        )
    except (KeyError, TypeError, ValueError):
        return None
