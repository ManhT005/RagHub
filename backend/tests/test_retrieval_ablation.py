from copy import deepcopy
from uuid import uuid4

import pytest
from raghub_core.domain.evaluation.metrics import recall_at_k, relevance_error_rates
from raghub_core.domain.retrieval.models import RetrievedChunk

from scripts.rag_dataset_audit import REQUIRED_CATEGORIES, REQUIRED_FORMATS, audit_dataset
from scripts.run_retrieval_ablation import grid_configs, score_case


def test_ablation_grid_and_multi_chunk_recall_are_not_document_hit_proxies():
    assert len(grid_configs()) == 27
    with pytest.raises(ValueError):
        grid_configs(candidate_counts=[1])
    assert recall_at_k(["a", "a", "b"], {"a", "b", "c"}) == pytest.approx(2 / 3)
    chunk = RetrievedChunk(uuid4(), uuid4(), uuid4(), "Fact.", "source", None, None, 0.03)
    row = score_case(
        {"id": "a", "answerable": True, "split": "calibration"},
        [chunk],
        {str(chunk.chunk_id), str(uuid4())},
        10,
    )
    assert row["hit@5"] == 1 and row["recall@5"] == 0.5
    assert row["context_tokens"] > 0 and row["search_ms"] == 10


def test_false_answer_and_reject_rates_have_explicit_class_denominators():
    result = relevance_error_rates(
        predicted_answerable=[True, False, True, True], actual_answerable=[True, True, False, False]
    )
    assert result == {"false_reject_rate": 0.5, "false_answer_rate": 1}
    assert (
        relevance_error_rates(predicted_answerable=[True], actual_answerable=[True])[
            "false_answer_rate"
        ]
        is None
    )


def test_dataset_audit_counts_families_and_requires_review_coverage_and_split_isolation():
    cases = [
        {
            "id": str(i),
            "family_id": str(i),
            "split": "holdout" if i % 3 == 0 else "calibration",
            "review_status": "reviewed",
            "answerable": True,
            "format": sorted(REQUIRED_FORMATS)[i % len(REQUIRED_FORMATS)],
            "categories": sorted(REQUIRED_CATEGORIES),
            "expected_facts": [{"fact": f"fact-{i}", "supporting_chunk_ids": [f"source-{i}"]}],
        }
        for i in range(200)
    ]
    assert audit_dataset(cases)["release_eligible"]
    duplicate = deepcopy(cases)
    duplicate[-1].update(family_id=duplicate[0]["family_id"], split="calibration")
    assert not audit_dataset(duplicate)["release_eligible"]
    drafts = deepcopy(cases)
    for row in drafts:
        row["review_status"] = "draft"
    assert audit_dataset(drafts)["reviewed_families"] == 0
    assert not audit_dataset(drafts)["release_eligible"]


def test_calibrator_uses_collector_identity_and_rejects_incorrect_override(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    from raghub_core.domain.retrieval.relevance import FEATURE_SCHEMA

    payload = {
        "metadata": {
            "dataset_hash": "data",
            "retrieval_config_hash": "config",
            "embedding_fingerprint": "fp",
            "mapping_version": "mapping",
            "feature_schema": FEATURE_SCHEMA,
        },
        "calibration": [
            {"fused_scores": [0.03], "answerable": True},
            {"fused_scores": [], "answerable": False},
        ],
        "holdout": [{"fused_scores": [9999], "answerable": True}],
    }
    scores, out = tmp_path / "scores.json", tmp_path / "artifact.json"
    scores.write_text(json.dumps(payload), encoding="utf-8")
    command = [
        sys.executable,
        str(Path(__file__).parents[1] / "scripts/calibrate_relevance.py"),
        "--scores",
        str(scores),
        "--out",
        str(out),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    artifact = json.loads(out.read_text(encoding="utf-8"))
    assert (
        artifact["embedding_fingerprint"] == "fp" and artifact["feature_schema"] == FEATURE_SCHEMA
    )
    assert artifact["feature_mean"][0] < 1
    result = subprocess.run([*command, "--dataset-hash", "wrong"], capture_output=True, text=True)
    assert result.returncode != 0 and "differs from collected" in result.stderr
