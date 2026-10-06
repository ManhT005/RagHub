import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "run_production_eval.py"


def _module():
    spec = importlib.util.spec_from_file_location("run_production_eval", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _case(overrides=None):
    base = {
        "answerable": True,
        "predicted_answerable": True,
        "retrieval_ms": 100.0,
        "chat_ms": 500.0,
        "hit@5": 1.0,
        "mrr@5": 1.0,
        "ndcg@5": 1.0,
        "cited_ids": ["C1"],
        "invalid_ids": [],
        "coverage": 1.0,
        "facts_recalled": 1.0,
        "forbidden_hit": [],
        "chat_error": None,
        "provider_error": False,
    }
    if overrides:
        base.update(overrides)
    return base


def test_provider_error_is_excluded_from_chat_quality_metrics():
    module = _module()
    cases = [
        _case(),
        _case(
            {
                "answerable": True,
                "predicted_answerable": True,
                "cited_ids": ["C99"],
                "invalid_ids": ["C99"],
                "coverage": 0.0,
                "facts_recalled": 0.0,
                "chat_error": {"code": "PROVIDER_RATE_LIMITED"},
                "provider_error": True,
            }
        ),
    ]

    summary = module.summarize_cases(cases)

    assert summary["provider_errors"] == 1
    assert summary["quality_chat_cases"] == 1
    assert summary["citation_precision"] == 1.0
    assert summary["citation_coverage_mean"] == 1.0
    assert summary["facts_recall"] == 1.0


def test_release_gate_fails_on_rejection_or_provider_errors():
    module = _module()
    summary = {
        "rejection_f1": 0.72,
        "citation_precision": 1.0,
        "answerable_direct_pass_rate": 1.0,
        "citation_coverage_mean": 0.9,
        "facts_recall": 0.9,
        "provider_errors": 1,
    }

    passed, checks = module.evaluate_release_gate(summary, module.DEFAULT_GATE_THRESHOLDS)

    assert not passed
    assert checks["rejection_f1"]["passed"] is False
    assert checks["provider_errors"]["passed"] is False


def test_release_gate_passes_when_all_thresholds_are_met():
    module = _module()
    summary = {
        "rejection_f1": 0.91,
        "citation_precision": 1.0,
        "answerable_direct_pass_rate": 0.95,
        "citation_coverage_mean": 0.9,
        "facts_recall": 0.9,
        "provider_errors": 0,
    }

    passed, checks = module.evaluate_release_gate(summary, module.DEFAULT_GATE_THRESHOLDS)

    assert passed
    assert all(item["passed"] for item in checks.values())


def test_optional_quality_and_latency_gates_fail_on_missing_or_regressed_metrics():
    module = _module()
    summary = {
        "rejection_f1": 1,
        "citation_precision": 1,
        "answerable_direct_pass_rate": 1,
        "citation_coverage_mean": 1,
        "facts_recall": 1,
        "provider_errors": 0,
        "mrr@5": 0.8,
        "retrieval_p95_ms": 1000,
    }
    thresholds = {
        **module.DEFAULT_GATE_THRESHOLDS,
        "mrr@5": 0.85,
        "retrieval_p95_ms": 500,
        "citation_support_precision": 0.9,
        "fact_support_recall": 0.85,
    }
    passed, checks = module.evaluate_release_gate(summary, thresholds)
    assert not passed
    assert not checks["mrr@5"]["passed"]
    assert not checks["retrieval_p95_ms"]["passed"]
    assert not checks["citation_support_precision"]["passed"]
    assert not checks["fact_support_recall"]["passed"]


def test_provider_error_detection_handles_nested_payloads():
    module = _module()

    assert module.is_provider_error({"error": {"code": "PROVIDER_TIMEOUT"}})
    assert module.is_provider_error({"code": "PUBLIC_CHAT_RATE_LIMITED"})
    assert not module.is_provider_error({"code": "VALIDATION_ERROR"})


def test_retrieve_context_emits_readiness_timing_sync():
    import asyncio
    from uuid import uuid4

    from raghub_core.api import RetrievalScope, RetrieveContextUseCase
    from raghub_core.domain.retrieval.models import RetrievedChunk

    from app.infrastructure.telemetry.adapter import InMemoryTelemetry
    from tests.core.fakes import FakeProviderResolver, FakeVectorStore

    class Search(FakeVectorStore):
        async def close(self):
            self.closed += 1

    class Readiness:
        async def filter_ready(self, scope, hits):
            return hits

    uid = uuid4()
    search = Search()
    search.hits = [RetrievedChunk(uid, uuid4(), uid, "safe text", "s.md", None, None, 0.5)]
    telemetry = InMemoryTelemetry()
    use_case = RetrieveContextUseCase(
        FakeProviderResolver(), Readiness(), lambda _: search, telemetry=telemetry
    )

    asyncio.run(use_case.retrieve(RetrievalScope(uuid4(), uuid4()), "query", 5))

    stages = {stage for stage, _, _ in telemetry.timings}
    assert {"query_embedding", "search", "readiness_filter"} <= stages
    assert ("retrieval_ready_hits", {"stage": "readiness"}, 1) in telemetry.counters


def test_chunk_search_emits_branch_and_fusion_telemetry_sync():
    import asyncio
    from types import SimpleNamespace
    from uuid import uuid4

    from app.infrastructure.elasticsearch.chunks import ChunkSearch
    from app.infrastructure.telemetry.adapter import InMemoryTelemetry

    org, ws = uuid4(), uuid4()
    doc, version = uuid4(), uuid4()
    hit = {
        "_source": {
            "document_id": str(doc),
            "document_version_id": str(version),
            "chunk_id": str(uuid4()),
            "content": "text",
            "source_name": "s.md",
            "page_number": None,
            "heading": None,
        },
        "_score": 1.0,
    }

    class Client:
        async def search(self, **kwargs):
            return {"hits": {"hits": [hit]}}

    telemetry = InMemoryTelemetry()
    search = object.__new__(ChunkSearch)
    search.settings = SimpleNamespace(
        rag_retrieval_candidates=25, rag_max_chunks_per_document=1, rag_rrf_k=17
    )
    search.index_name = "idx"
    search.telemetry = telemetry
    search.client = Client()

    asyncio.run(
        search.search(
            organization_id=org,
            workspace_id=ws,
            query="q",
            query_vector=[1.0, 0.0],
            limit=5,
        )
    )

    stages = {stage for stage, _, _ in telemetry.timings}
    assert {
        "retrieval_es_bm25",
        "retrieval_es_vector",
        "retrieval_rrf_diversity",
        "retrieval_es_total",
    } <= stages
    assert ("retrieval_fused_hits", {"stage": "retrieval"}, 1) in telemetry.counters
