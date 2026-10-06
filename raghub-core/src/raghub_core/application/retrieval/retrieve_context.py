import math
import time
from collections.abc import Awaitable, Callable

from raghub_core.domain.errors import CoreError
from raghub_core.domain.providers.errors import ProviderRateLimitError, ProviderUnavailableError
from raghub_core.domain.retrieval.hybrid import (
    RERANK_SOURCE_COUNT,
    RERANK_TOP_N,
    RETRIEVAL_CANDIDATES,
    ContextBundle,
    build_context_bundle,
    normalize_query,
)
from raghub_core.domain.retrieval.models import RetrievalAssessment, RetrievalScope, RetrievedChunk
from raghub_core.domain.retrieval.relevance import RelevanceDecision
from raghub_core.ports.embedding_quota import (
    EmbeddingQuotaPort,
    QuotaBackendUnavailableError,
    QuotaDepletedError,
)
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
        quota: EmbeddingQuotaPort | None = None,
        neighbor_expansion: Callable[..., Awaitable[list[RetrievedChunk]]] | None = None,
        relevance_factory: Callable[[EmbeddingRuntime], RelevanceFn] | None = None,
    ) -> None:
        self.providers, self.readiness, self.make_search = providers, readiness, make_search
        self.rerank, self.relevance, self.rerank_top_n = rerank, relevance, rerank_top_n
        self.telemetry = telemetry
        self.relevance_factory = relevance_factory
        self.quota = quota
        self.neighbor_expansion = neighbor_expansion

    async def retrieve(
        self,
        scope: RetrievalScope,
        query: str,
        limit: int,
        *,
        rerank: RerankFn | None = None,
        relevance: RelevanceFn | None = None,
        rerank_top_n: int | None = None,
        relevance_observer: Callable[[RelevanceDecision], None] | None = None,
    ) -> list[RetrievedChunk]:
        rerank = self.rerank if rerank is None else rerank
        relevance = self.relevance if relevance is None else relevance
        top_n = self.rerank_top_n if rerank_top_n is None else rerank_top_n
        telemetry = self.telemetry
        mark = time.perf_counter()
        runtime = await self.providers.resolve_embedding(scope)
        if self.relevance_factory is not None:
            relevance = self.relevance_factory(runtime)
        normalized = normalize_query(query)
        if self.quota is not None and runtime.quota_scope:
            from raghub_core.domain.embedding.quota import estimate_tokens

            try:
                await self.quota.acquire(
                    scope=runtime.quota_scope,
                    tokens=estimate_tokens(len(normalized)),
                    background=False,
                )
            except QuotaDepletedError as exc:
                raise ProviderRateLimitError("Query embedding capacity exhausted.") from exc
            except QuotaBackendUnavailableError as exc:
                raise ProviderUnavailableError("Query quota coordinator unavailable.") from exc
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
            if relevance is not None:
                mark = time.perf_counter()
                decision = relevance([hit.score for hit in ranked])
                if relevance_observer is not None:
                    relevance_observer(decision)
                if telemetry is not None:
                    telemetry.timing(
                        "relevance_gate",
                        (time.perf_counter() - mark) * 1000,
                        {"stage": "relevance"},
                    )
                    telemetry.counter(
                        "relevance_rejected" if not decision.accepted else "relevance_accepted",
                        {"stage": "relevance"},
                    )
                if not decision.accepted:
                    return []  # REJECT feeds the existing empty-context fallback
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
            mark = time.perf_counter()
            ready = await self.readiness.filter_ready(scope, ranked)
            if telemetry is not None:
                telemetry.timing(
                    "readiness_filter", (time.perf_counter() - mark) * 1000, {"stage": "readiness"}
                )
                telemetry.counter("retrieval_ready_hits", {"stage": "readiness"}, len(ready))
                if not ready:
                    telemetry.counter("empty_context", {"stage": "context"})
            if self.neighbor_expansion is not None and ready:
                mark = time.perf_counter()
                try:
                    expanded = await self.neighbor_expansion(
                        runtime, scope, ready[: max(1, limit // 2)]
                    )
                    ready = await self.readiness.filter_ready(scope, expanded)
                except Exception:
                    if telemetry is not None:
                        telemetry.counter("neighbor_fallback", {"stage": "context"})
                if telemetry is not None:
                    telemetry.timing("neighbor_expansion", (time.perf_counter() - mark) * 1000, {})
            return ready[:limit]
        except CoreError:
            raise
        except Exception as exc:
            raise CoreError("SEARCH_UNAVAILABLE", "Search is temporarily unavailable.") from exc
        finally:
            await search.close()

    async def assess(self, scope, query, limit) -> RetrievalAssessment:
        decisions = []
        hits = await self.retrieve(scope, query, limit, relevance_observer=decisions.append)
        return RetrievalAssessment(tuple(hits), decisions[0].confidence if decisions else None)

    async def execute(self, scope: RetrievalScope, query: str, limit: int) -> ContextBundle:
        return build_context_bundle(await self.retrieve(scope, query, limit))
