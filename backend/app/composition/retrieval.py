"""Compose retrieval hooks from feature flags (all default off)."""

from functools import lru_cache
from pathlib import Path

from raghub_core.api import RetrieveContextUseCase
from raghub_core.domain.retrieval.evidence import select_evidence
from raghub_core.domain.retrieval.hybrid import MAPPING_VERSION
from raghub_core.domain.retrieval.relevance import FEATURE_SCHEMA, decide
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.ai.local_reranker import LocalCrossEncoderReranker
from app.infrastructure.elasticsearch.chunks import ChunkSearch
from app.infrastructure.elasticsearch.neighbors import NeighborExpansion
from app.infrastructure.elasticsearch.vector_store import ElasticsearchVectorSearch
from app.infrastructure.persistence.readiness import DocumentReadinessAdapter
from app.infrastructure.providers import ProviderResolverAdapter
from app.infrastructure.redis.query_quota import QueryQuota
from app.infrastructure.rerank import WorkspaceRerankResolver, record_rerank_status
from app.infrastructure.telemetry.adapter import LoggingTelemetry
from app.modules.ai_providers.resolver import ProviderResolver
from app.modules.search.relevance import (
    dataset_hash,
    load_relevance_artifact,
    retrieval_config_hash,
)


@lru_cache(maxsize=8)
def local_reranker(snapshot_path, expected_sha256, timeout_seconds):
    return LocalCrossEncoderReranker(
        snapshot_path=snapshot_path,
        expected_sha256=expected_sha256,
        timeout_seconds=timeout_seconds,
    )


def _artifact_path() -> Path:
    settings = get_settings()
    if settings.rag_relevance_artifact_path:
        return Path(settings.rag_relevance_artifact_path)
    backend = Path(__file__).resolve().parents[2]
    return (
        backend
        / "tests"
        / "fixtures"
        / "rag_golden"
        / f"relevance_{settings.rag_relevance_config_version}.json"
    )


def retrieval_use_case(session: AsyncSession) -> RetrieveContextUseCase:
    settings = get_settings()
    rerank = None
    if settings.rag_reranker_enabled:
        adapter = local_reranker(
            snapshot_path=settings.rag_reranker_snapshot_path,
            expected_sha256=settings.rag_reranker_expected_sha256,
            timeout_seconds=settings.rag_reranker_timeout_seconds,
        )
        top_n = settings.rag_rerank_top_n

        async def rerank(query: str, candidates: list, top_n: int = top_n):  # type: ignore[no-redef]
            return await adapter.rerank(query=query, candidates=candidates, top_n=top_n)

    relevance_factory = None
    if settings.rag_relevance_gate_enabled:
        artifact = load_relevance_artifact(
            _artifact_path(), expected_version=settings.rag_relevance_config_version
        )
        qa_path = (
            Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "rag_golden" / "qa.json"
        )
        live_dataset = dataset_hash(qa_path) if qa_path.exists() else ""
        live_config = retrieval_config_hash(
            candidates=settings.rag_retrieval_candidates,
            rrf_k=settings.rag_rrf_k,
            mapping_version=MAPPING_VERSION,
            max_per_document=settings.rag_max_chunks_per_document,
        )

        def relevance_factory(runtime):
            def relevance(scores: list[float], _artifact=artifact):
                from raghub_core.domain.retrieval.relevance import RelevanceDecision

                if _artifact is None:
                    return RelevanceDecision(accepted=True, confidence=1.0, calibrated=False)
                return decide(
                    _artifact,
                    scores,
                    enabled_flag=True,
                    dataset_hash=live_dataset,
                    retrieval_config_hash=live_config,
                    embedding_fingerprint=runtime.fingerprint,
                    mapping_version=MAPPING_VERSION,
                    feature_schema=FEATURE_SCHEMA,
                )

            return relevance

    telemetry = LoggingTelemetry()
    providers = ProviderResolver(session)
    return RetrieveContextUseCase(
        ProviderResolverAdapter(providers),
        DocumentReadinessAdapter(session),
        lambda runtime: ElasticsearchVectorSearch(
            ChunkSearch(index_name=runtime.index_name, telemetry=telemetry)
        ),
        rerank_resolver=WorkspaceRerankResolver(session, providers),
        on_rerank_status=record_rerank_status,
        rerank=rerank,
        relevance_factory=relevance_factory,
        rerank_top_n=settings.rag_rerank_top_n,
        adaptive_rerank=settings.rag_adaptive_rerank_enabled,
        confidence_high_threshold=settings.rag_confidence_high_threshold,
        candidate_count=settings.rag_retrieval_candidates,
        rerank_source_count=settings.rag_rerank_source_count,
        rerank_candidate_cap=settings.rag_rerank_source_count
        if settings.rag_hardware_profile != "custom"
        else None,
        evidence_selector=(
            lambda query, hits, limit: select_evidence(
                query, hits, limit, max_tokens=settings.rag_max_context_tokens
            )
        )
        if settings.rag_evidence_selection_enabled
        else None,
        telemetry=telemetry,
        quota=QueryQuota(settings),
        neighbor_expansion=NeighborExpansion(settings).expand
        if settings.rag_neighbor_expansion_enabled
        else None,
    )
