from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from raghub_core.api import RetrievalScope, RetrieveContextUseCase
from raghub_core.domain.retrieval.confidence import ConfidenceBand, confidence_band
from raghub_core.domain.retrieval.evidence import select_evidence
from raghub_core.domain.retrieval.models import RetrievedChunk
from raghub_core.domain.retrieval.relevance import RelevanceArtifact, RelevanceDecision, decide

from .fakes import FakeProviderResolver, FakeVectorStore


def hit(text, doc=None, version=None, index=0):
    return RetrievedChunk(
        doc or uuid4(), version or uuid4(), uuid4(), text, "source.txt", None, None, 0.03, index
    )


def test_evidence_dedup_keeps_distinct_same_document_facts_and_raw_overlap_slice():
    doc, version = uuid4(), uuid4()
    overlap = "one two three four five six seven eight nine ten"
    a = hit("alpha cost 100 " + overlap, doc, version, 0)
    b = hit(overlap + " beta deadline 2027", doc, version, 1)
    duplicate = replace(a, chunk_id=uuid4())
    selected = select_evidence("alpha cost beta deadline", [a, duplicate, b], 5)
    assert len(selected) == 2
    assert selected[0] == a and selected[1].content == "beta deadline 2027"
    assert b.content.endswith(selected[1].content)


def test_evidence_skips_an_oversize_item_to_keep_useful_smaller_evidence():
    large, small = hit("word " * 2000), hit("Cost is 100.")
    assert select_evidence("cost", [large, small], 5, max_tokens=100) == [small]
    assert select_evidence("cost", [large], 5, max_tokens=100) == [large]
    assert select_evidence("cost", [small], 0) == []


@pytest.mark.parametrize(
    "decision, expected",
    [
        (RelevanceDecision(True, 1, calibrated=False), ConfidenceBand.UNKNOWN),
        (RelevanceDecision(True, 0.9), ConfidenceBand.HIGH),
        (RelevanceDecision(True, 0.7), ConfidenceBand.MEDIUM),
        (RelevanceDecision(False, 0.2), ConfidenceBand.LOW),
    ],
)
def test_confidence_router_requires_calibration(decision, expected):
    assert confidence_band(decision) == expected


@pytest.mark.parametrize(
    "confidence, calibrated, calls", [(0.95, True, 0), (0.6, True, 1), (1, False, 1)]
)
async def test_adaptive_rerank_skips_resolution_only_for_calibrated_high_confidence(
    confidence, calibrated, calls
):
    class Search(FakeVectorStore):
        async def close(self):
            pass

    search = Search()
    search.hits = [hit("ready fact")]
    readiness = type(
        "Ready", (), {"filter_ready": AsyncMock(side_effect=lambda scope, hits: hits)}
    )()
    resolver = type("Resolver", (), {"resolve_rerank": AsyncMock(return_value=None)})()
    rerank = AsyncMock(side_effect=ValueError("malformed rerank"))
    runtime = RetrieveContextUseCase(
        FakeProviderResolver(),
        readiness,
        lambda _: search,
        rerank_resolver=resolver,
        rerank=rerank,
        adaptive_rerank=True,
        relevance=lambda scores: RelevanceDecision(True, confidence, calibrated=calibrated),
    )
    result = await runtime.retrieve(RetrievalScope(uuid4(), uuid4()), "query", 5)
    assert result == search.hits
    assert resolver.resolve_rerank.await_count == rerank.await_count == calls


async def test_confidence_excludes_unready_hits_and_neighbors_expand_selected_evidence_only():
    class Search(FakeVectorStore):
        async def close(self):
            pass

    search = Search()
    search.hits = [hit("unready"), hit("ready"), hit("duplicate"), hit("unused")]
    readiness = type(
        "Ready",
        (),
        {
            "filter_ready": AsyncMock(
                side_effect=lambda scope, hits: [h for h in hits if h.content != "unready"]
            )
        },
    )()
    observed = []
    expand = AsyncMock(side_effect=lambda runtime, scope, seeds: seeds)
    use_case = RetrieveContextUseCase(
        FakeProviderResolver(),
        readiness,
        lambda _: search,
        relevance=lambda scores: observed.append(scores) or RelevanceDecision(True, 0.9),
        evidence_selector=lambda query, hits, limit: hits[:limit],
        neighbor_expansion=expand,
    )
    scope = RetrievalScope(uuid4(), uuid4())
    result = await use_case.retrieve(scope, "query", 1)
    assert len(observed[0]) == 3 and result[0].content == "ready"
    assert expand.await_args.args[2] == result


def test_artifact_mapping_and_feature_schema_mismatch_is_uncalibrated():
    artifact = RelevanceArtifact(
        "v",
        ("fused_1",),
        (1,),
        0,
        0.5,
        "data",
        "config",
        "fp",
        mapping_version="mapping-v1",
        feature_schema="schema-v1",
    )
    result = decide(
        artifact,
        [0.03],
        enabled_flag=True,
        dataset_hash="data",
        retrieval_config_hash="config",
        embedding_fingerprint="fp",
        mapping_version="mapping-v2",
        feature_schema="schema-v1",
    )
    assert result.accepted and not result.calibrated
    assert confidence_band(result) == ConfidenceBand.UNKNOWN
