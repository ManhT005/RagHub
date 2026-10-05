"""Relevance rejection and reranker canary (offline, flags default off)."""
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from raghub_core.domain.retrieval.models import RetrievedChunk
from raghub_core.domain.retrieval.relevance import (
    RelevanceArtifact,
    decide,
    empty_artifact,
    gate_enabled,
    score_candidates,
    sigmoid,
)

from app.modules.search.relevance import load_relevance_artifact


def _artifact(**overrides) -> RelevanceArtifact:
    base = {
        "version": "baseline-v1",
        "feature_names": ("fused_1", "margin_12", "mean_top3", "n_results"),
        "weights": (8.0, 4.0, 2.0, 0.1),
        "intercept": -1.0,
        "threshold": 0.5,
        "dataset_hash": "qa1",
        "retrieval_config_hash": "cfg1",
        "embedding_fingerprint": "fp",
    }
    base.update(overrides)
    return RelevanceArtifact(**base)


def test_sigmoid_pure_math_and_threshold_boundary():
    assert sigmoid(1000.0) == 1.0 and sigmoid(-1000.0) == 0.0
    strong = decide(_artifact(), [0.5, 0.1, 0.05], enabled_flag=True,
                    dataset_hash="qa1", retrieval_config_hash="cfg1")
    assert strong.accepted and 0.0 <= strong.confidence <= 1.0
    weak = decide(_artifact(), [0.001], enabled_flag=True,
                  dataset_hash="qa1", retrieval_config_hash="cfg1")
    assert not weak.accepted
    assert decide(_artifact(), [], enabled_flag=True,
                  dataset_hash="qa1", retrieval_config_hash="cfg1").accepted is False


def test_hash_mismatch_keeps_gate_off():
    artifact = _artifact()
    assert gate_enabled(artifact, enabled_flag=True, dataset_hash="qa1",
                        retrieval_config_hash="cfg1") is True
    assert gate_enabled(artifact, enabled_flag=False, dataset_hash="qa1",
                        retrieval_config_hash="cfg1") is False
    assert gate_enabled(None, enabled_flag=True, dataset_hash="qa1",
                        retrieval_config_hash="cfg1") is False
    assert gate_enabled(artifact, enabled_flag=True, dataset_hash="other",
                        retrieval_config_hash="cfg1") is False
    # Mismatch never rejects: legacy top-k behavior.
    decision = decide(artifact, [0.0001], enabled_flag=True,
                      dataset_hash="other", retrieval_config_hash="cfg1")
    assert decision.accepted is True


def test_empty_artifact_never_rejects():
    artifact = empty_artifact("baseline-v1")
    assert decide(artifact, [0.0], enabled_flag=True,
                  dataset_hash="", retrieval_config_hash="").accepted is True


def test_score_monotonic_in_top_score():
    artifact = _artifact()
    assert score_candidates(artifact, [0.4, 0.1]) > score_candidates(artifact, [0.2, 0.1])


def test_artifact_loader_rejects_bad_files(tmp_path: Path):
    good = {
        "version": "baseline-v1",
        "feature_names": ["fused_1"],
        "weights": [1.0],
        "intercept": 0.0,
        "threshold": 0.5,
        "dataset_hash": "qa1",
        "retrieval_config_hash": "cfg1",
        "embedding_fingerprint": "fp",
    }
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    assert load_relevance_artifact(path, expected_version="baseline-v1") is not None
    assert load_relevance_artifact(path, expected_version="other") is None
    assert (
        load_relevance_artifact(tmp_path / "missing.json", expected_version="baseline-v1")
        is None
    )
    bad = dict(good, threshold=1.5)
    path.write_text(json.dumps(bad), encoding="utf-8")
    assert load_relevance_artifact(path, expected_version="baseline-v1") is None
    path.write_text("{not json", encoding="utf-8")
    assert load_relevance_artifact(path, expected_version="baseline-v1") is None


def _chunk(score: float) -> RetrievedChunk:
    uid = uuid4()
    return RetrievedChunk(uid, uuid4(), uid, "text", "s.md", None, None, score)


async def test_reranker_reorders_and_truncates():
    from raghub_core.api import RetrievalScope, RetrieveContextUseCase

    from tests.core.fakes import FakeProviderResolver, FakeVectorStore

    providers = FakeProviderResolver()

    class Search(FakeVectorStore):
        async def close(self):
            self.closed += 1

    search = Search()
    hits = [_chunk(0.1), _chunk(0.5), _chunk(0.3)]
    search.hits = hits

    async def reverse_rerank(query, candidates, top_n):
        return list(reversed(candidates))[:top_n]

    scope = RetrievalScope(uuid4(), uuid4())
    use_case = RetrieveContextUseCase(providers, _ReadyAll(), lambda _: search)
    ranked = await use_case.retrieve(scope, "q", 5, rerank=reverse_rerank, rerank_top_n=2)
    assert [h.score for h in ranked] == [0.3, 0.5]


async def test_reranker_timeout_falls_back_to_fusion():
    from raghub_core.api import RetrievalScope, RetrieveContextUseCase
    from raghub_core.ports.reranker import RerankerTimeoutError

    from tests.core.fakes import FakeProviderResolver, FakeVectorStore

    providers = FakeProviderResolver()

    class Search(FakeVectorStore):
        async def close(self):
            self.closed += 1

    search = Search()
    search.hits = [_chunk(0.2), _chunk(0.9)]

    async def slow(query, candidates, top_n):
        raise RerankerTimeoutError("slow")

    scope = RetrievalScope(uuid4(), uuid4())
    use_case = RetrieveContextUseCase(providers, _ReadyAll(), lambda _: search)
    ranked = await use_case.retrieve(scope, "q", 5, rerank=slow)
    assert [h.score for h in ranked] == [0.2, 0.9]


async def test_relevance_reject_returns_empty_before_readiness():
    from raghub_core.api import RetrievalScope, RetrieveContextUseCase
    from raghub_core.domain.retrieval.relevance import RelevanceDecision

    from tests.core.fakes import FakeProviderResolver, FakeVectorStore

    providers = FakeProviderResolver()

    class Search(FakeVectorStore):
        async def close(self):
            self.closed += 1

    search = Search()
    search.hits = [_chunk(0.9)]

    class Readiness:
        def __init__(self):
            self.calls = 0

        async def filter_ready(self, scope, hits):
            self.calls += 1
            return hits

    readiness = Readiness()
    scope = RetrievalScope(uuid4(), uuid4())
    use_case = RetrieveContextUseCase(providers, readiness, lambda _: search)
    rejected = await use_case.retrieve(
        scope, "q", 5, relevance=lambda scores: RelevanceDecision(False, 0.1)
    )
    assert rejected == [] and readiness.calls == 0


class _ReadyAll:
    async def filter_ready(self, scope, hits):
        return hits


def test_reranker_model_is_pinned():
    from app.infrastructure.ai.local_reranker import MODEL_ID, MODEL_REVISION

    assert MODEL_ID == "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    assert MODEL_REVISION == "main"


def test_calibration_cli_produces_loadable_artifact(tmp_path: Path):
    rows = (
        [{"fused_scores": [0.4 + i * 0.01, 0.2], "answerable": True} for i in range(10)]
        + [{"fused_scores": [0.01, 0.005], "answerable": False} for _ in range(10)]
    )
    scores_path = tmp_path / "scores.json"
    scores_path.write_text(json.dumps(rows), encoding="utf-8")
    out_path = tmp_path / "artifact.json"
    script = Path(__file__).parent.parent / "scripts" / "calibrate_relevance.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--scores", str(scores_path), "--out", str(out_path),
         "--dataset-hash", "qa1", "--config-hash", "cfg1", "--version", "baseline-v1"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["train_rejection_f1"] == 1.0
    artifact = load_relevance_artifact(out_path, expected_version="baseline-v1")
    assert artifact is not None and artifact.dataset_hash == "qa1"


def test_flags_default_off():
    from app.core.config import Settings

    settings = Settings()
    assert settings.rag_relevance_gate_enabled is False
    assert settings.rag_reranker_enabled is False
    assert settings.rag_rerank_top_n == 8
    assert settings.rag_relevance_config_version == "baseline-v1"
