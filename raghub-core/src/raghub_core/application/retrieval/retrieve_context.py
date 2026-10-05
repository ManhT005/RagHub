import math
from collections.abc import Callable

from raghub_core.domain.errors import CoreError
from raghub_core.domain.retrieval.hybrid import (
    RETRIEVAL_CANDIDATES,
    ContextBundle,
    build_context_bundle,
)
from raghub_core.domain.retrieval.models import RetrievalScope, RetrievedChunk
from raghub_core.ports.provider_resolver import EmbeddingRuntime, ProviderResolverPort
from raghub_core.ports.retrieval import DocumentReadinessPort
from raghub_core.ports.vector_store import VectorSearchPort


class RetrieveContextUseCase:
    def __init__(
        self,
        providers: ProviderResolverPort,
        readiness: DocumentReadinessPort,
        make_search: Callable[[EmbeddingRuntime], VectorSearchPort],
    ) -> None:
        self.providers, self.readiness, self.make_search = providers, readiness, make_search

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
            candidates = await search.search(scope, query, vector, max(limit, RETRIEVAL_CANDIDATES))
            return (await self.readiness.filter_ready(scope, candidates))[:limit]
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
