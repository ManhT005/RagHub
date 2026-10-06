import asyncio
import math
from collections.abc import Callable

from raghub_core.domain.errors import CoreError
from raghub_core.domain.providers.rerank import validated_rerank_indices
from raghub_core.domain.retrieval.hybrid import (
    RETRIEVAL_CANDIDATES,
    ContextBundle,
    build_context_bundle,
)
from raghub_core.domain.retrieval.models import RetrievalScope, RetrievedChunk
from raghub_core.ports.provider_resolver import EmbeddingRuntime, ProviderResolverPort
from raghub_core.ports.rerank import RerankResolverPort
from raghub_core.ports.retrieval import DocumentReadinessPort
from raghub_core.ports.vector_store import VectorSearchPort


class RetrieveContextUseCase:
    def __init__(
        self,
        providers: ProviderResolverPort,
        readiness: DocumentReadinessPort,
        make_search: Callable[[EmbeddingRuntime], VectorSearchPort],
        rerank: RerankResolverPort | None = None,
        on_rerank_status: Callable[[str], None] | None = None,
    ) -> None:
        self.providers, self.readiness, self.make_search = providers, readiness, make_search
        self.rerank, self.on_rerank_status = rerank, on_rerank_status

    def _rerank_status(self, status):
        if self.on_rerank_status:
            self.on_rerank_status(status)

    async def retrieve(self, scope: RetrievalScope, query: str, limit: int) -> list[RetrievedChunk]:
        runtime = await self.providers.resolve_embedding(scope)
        vector = await runtime.provider.embed_query(query)
        if len(vector) != runtime.dimension or not all(math.isfinite(x) for x in vector):
            raise CoreError(
                "PROVIDER_INVALID_RESPONSE",
                "Query embedding dimension does not match the active index.",
            )
        search = self.make_search(runtime)
        try:
            rerank_runtime = None
            if self.rerank:
                try:
                    rerank_runtime = await asyncio.wait_for(self.rerank.resolve_rerank(scope), 5)
                except Exception:
                    self._rerank_status("DEGRADED_RESOLUTION")
            candidate_limit = max(limit, RETRIEVAL_CANDIDATES)
            if rerank_runtime:
                candidate_limit = max(candidate_limit, min(200, rerank_runtime.candidate_limit))
            candidates = await search.search(scope, query, vector, candidate_limit)
            ready = await self.readiness.filter_ready(scope, candidates)
            if rerank_runtime and ready:
                selected = ready[: min(200, rerank_runtime.candidate_limit)]
                top_n = min(limit, rerank_runtime.top_n, len(selected))
                try:
                    result = await asyncio.wait_for(
                        rerank_runtime.provider.rerank(
                            query=query,
                            documents=[chunk.content for chunk in selected],
                            top_n=top_n,
                        ),
                        min(30, max(0.1, rerank_runtime.timeout_seconds)),
                    )
                    indices = validated_rerank_indices(result, len(selected), top_n)
                    self._rerank_status("OK")
                    return [selected[index] for index in indices]
                except Exception:
                    self._rerank_status("DEGRADED_REQUEST")
            return ready[:limit]
        except CoreError:
            raise
        except Exception as exc:
            raise CoreError("SEARCH_UNAVAILABLE", "Search is temporarily unavailable.") from exc
        finally:
            await search.close()

    async def execute(self, scope: RetrievalScope, query: str, limit: int) -> ContextBundle:
        return build_context_bundle(await self.retrieve(scope, query, limit))
