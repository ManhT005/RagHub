"""Compose retrieval hooks from feature flags (all default off)."""

from pathlib import Path

from raghub_core.api import RetrieveContextUseCase
from raghub_core.domain.retrieval.hybrid import MAPPING_VERSION
from raghub_core.domain.retrieval.relevance import decide
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.ai.local_reranker import LocalCrossEncoderReranker
from app.infrastructure.elasticsearch.chunks import ChunkSearch
from app.infrastructure.elasticsearch.vector_store import ElasticsearchVectorSearch
from app.infrastructure.persistence.readiness import DocumentReadinessAdapter
from app.infrastructure.providers import ProviderResolverAdapter
from app.infrastructure.rerank import WorkspaceRerankResolver, record_rerank_status
from app.infrastructure.telemetry.adapter import LoggingTelemetry
from app.modules.ai_providers.resolver import ProviderResolver
from app.modules.search.relevance import (
    dataset_hash,
    load_relevance_artifact,
    retrieval_config_hash,
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
    providers = ProviderResolver(session)
    rerank = None
    if settings.rag_reranker_enabled:
        adapter = LocalCrossEncoderReranker()
        top_n = settings.rag_rerank_top_n

        async def rerank(query: str, candidates: list, top_n: int = top_n):  # type: ignore[no-redef]
            return await adapter.rerank(query=query, candidates=candidates, top_n=top_n)

    relevance = None
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
        )

        def relevance(scores: list[float], _artifact=artifact):  # type: ignore[misc]
            from raghub_core.domain.retrieval.relevance import RelevanceDecision

            if _artifact is None:
                return RelevanceDecision(accepted=True, confidence=1.0)
            return decide(
                _artifact,
                scores,
                enabled_flag=True,
                dataset_hash=live_dataset,
                retrieval_config_hash=live_config,
            )

    telemetry = LoggingTelemetry()
    return RetrieveContextUseCase(
        ProviderResolverAdapter(providers),
        DocumentReadinessAdapter(session),
        lambda runtime: ElasticsearchVectorSearch(
            ChunkSearch(index_name=runtime.index_name, telemetry=telemetry)
        ),
        WorkspaceRerankResolver(session, providers),
        record_rerank_status,
        rerank=rerank,
        relevance=relevance,
        rerank_top_n=settings.rag_rerank_top_n,
        telemetry=telemetry,
    )
