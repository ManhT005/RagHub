import math
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
    ) -> None:
        self.providers, self.readiness, self.make_search = providers, readiness, make_search
        self.rerank, self.relevance, self.rerank_top_n = rerank, relevance, rerank_top_n

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
        runtime = await self.providers.resolve_embedding(scope)
        normalized = normalize_query(query)
        vector = await runtime.provider.embed_query(normalized)
        if len(vector) != runtime.dimension or not all(math.isfinite(x) for x in vector):
            raise CoreError(
                "PROVIDER_INVALID_RESPONSE",
                "Query embedding dimension does not match the active index.",
            )
        search = self.make_search(runtime)
        try:
            fetch = max(limit, RETRIEVAL_CANDIDATES, RERANK_SOURCE_COUNT if rerank else 0)
            ranked = await search.search(scope, normalized, vector, fetch)
            if rerank is not None:
                try:
                    ranked = await rerank(normalized, ranked[:RERANK_SOURCE_COUNT], top_n)
                except (RerankerTimeoutError, RuntimeError):
                    pass  # fusion fallback: reranker is observe/canary-only
            if relevance is not None and not relevance([hit.score for hit in ranked]).accepted:
                return []  # REJECT feeds the existing empty-context fallback
            return (await self.readiness.filter_ready(scope, ranked))[:limit]
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
