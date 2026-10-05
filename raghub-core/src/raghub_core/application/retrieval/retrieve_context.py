import math
import time
from collections.abc import Awaitable, Callable

from raghub_core.domain.errors import CoreError
from raghub_core.domain.retrieval.hybrid import (
    RERANK_SOURCE_COUNT,
    RERANK_TOP_N,
    RETRIEVAL_CANDIDATES,
    ContextBundle,
    build_context_bundle,
    normalize_query,
)
from raghub_core.domain.retrieval.models import RetrievalScope, RetrievedChunk
from raghub_core.domain.retrieval.relevance import RelevanceDecision
from raghub_core.ports.provider_resolver import EmbeddingRuntime, ProviderResolverPort
from raghub_core.ports.reranker import RerankerTimeoutError
from raghub_core.ports.retrieval import DocumentReadinessPort
from raghub_core.ports.telemetry import TelemetryPort
from raghub_core.ports.vector_store import VectorSearchPort

RerankFn = Callable[[str, list[RetrievedChunk], int], Awaitable[list[RetrievedChunk]]]
RelevanceFn = Callable[[list[float]], RelevanceDecision]


class RetrieveContextUseCase:
    def __init__(
        self,
        providers: ProviderResolverPort,
        readiness: DocumentReadinessPort,
        make_search: Callable[[EmbeddingRuntime], VectorSearchPort],
        *,
        rerank: RerankFn | None = None,
        relevance: RelevanceFn | None = None,
        rerank_top_n: int = RERANK_TOP_N,
        telemetry: TelemetryPort | None = None,
    ) -> None:
        self.providers, self.readiness, self.make_search = providers, readiness, make_search
        self.rerank, self.relevance, self.rerank_top_n = rerank, relevance, rerank_top_n
        self.telemetry = telemetry

    async def retrieve(
        self,
        scope: RetrievalScope,
        query: str,
        limit: int,
        *,
        rerank: RerankFn | None = None,
        relevance: RelevanceFn | None = None,
        rerank_top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        rerank = self.rerank if rerank is None else rerank
        relevance = self.relevance if relevance is None else relevance
        top_n = self.rerank_top_n if rerank_top_n is None else rerank_top_n
        telemetry = self.telemetry
        mark = time.perf_counter()
        runtime = await self.providers.resolve_embedding(scope)
        normalized = normalize_query(query)
        vector = await runtime.provider.embed_query(normalized)
        if telemetry is not None:
            telemetry.timing("query_embedding", (time.perf_counter() - mark) * 1000, {})
        if len(vector) != runtime.dimension or not all(math.isfinite(x) for x in vector):
            raise CoreError(
                "PROVIDER_INVALID_RESPONSE",
                "Query embedding dimension does not match the active index.",
            )
        search = self.make_search(runtime)
        try:
            fetch = max(limit, RETRIEVAL_CANDIDATES, RERANK_SOURCE_COUNT if rerank else 0)
            mark = time.perf_counter()
            ranked = await search.search(scope, normalized, vector, fetch)
            if telemetry is not None:
                telemetry.timing("search", (time.perf_counter() - mark) * 1000, {})
            if rerank is not None:
                mark = time.perf_counter()
                try:
                    ranked = await rerank(normalized, ranked[:RERANK_SOURCE_COUNT], top_n)
                except (RerankerTimeoutError, RuntimeError):
                    if telemetry is not None:
                        telemetry.counter("rerank_fallback", {"stage": "rerank"})
                finally:
                    if telemetry is not None:
                        telemetry.timing("rerank", (time.perf_counter() - mark) * 1000, {})
            if relevance is not None:
                decision = relevance([hit.score for hit in ranked])
                if telemetry is not None:
                    telemetry.counter(
                        "relevance_rejected" if not decision.accepted else "relevance_accepted",
                        {"stage": "relevance"},
                    )
                if not decision.accepted:
                    return []  # REJECT feeds the existing empty-context fallback
            ready = await self.readiness.filter_ready(scope, ranked)
            if telemetry is not None and not ready:
                telemetry.counter("empty_context", {"stage": "context"})
            return ready[:limit]
        except CoreError:
            raise
        except Exception as exc:
            raise CoreError("SEARCH_UNAVAILABLE", "Search is temporarily unavailable.") from exc
        finally:
            await search.close()

    async def execute(self, scope: RetrievalScope, query: str, limit: int) -> ContextBundle:
        return build_context_bundle(
            await self.retrieve(scope, query, limit)
        )
