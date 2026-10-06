from uuid import uuid4

import pytest

from raghub_core.api import CoreError, RetrievalScope, RetrieveContextUseCase, RetrievedChunk

from .fakes import FakeProviderResolver, FakeVectorStore


class Readiness:
    def __init__(self):
        self.calls = []
        self.ready_pairs = set()

    async def filter_ready(self, scope, hits):
        self.calls.append(scope)
        return [
            hit for hit in hits if (hit.document_id, hit.document_version_id) in self.ready_pairs
        ]


class Search(FakeVectorStore):
    async def close(self):
        self.closed += 1


def hit(document_id=None):
    return RetrievedChunk(
        document_id or uuid4(), uuid4(), uuid4(), "knowledge", "guide.md", None, "Guide", 0.03
    )


async def test_retrieval_checks_exact_ready_pairs_before_applying_limit():
    providers, store, readiness = FakeProviderResolver(), Search(), Readiness()
    scope = RetrievalScope(uuid4(), uuid4())
    ready = hit()
    stale = hit(ready.document_id)
    store.hits = [stale, ready]
    readiness.ready_pairs = {(ready.document_id, ready.document_version_id)}
    use_case = RetrieveContextUseCase(providers, readiness, lambda _: store)
    assert await use_case.retrieve(scope, "question", 1) == [ready]
    assert providers.scopes == readiness.calls == [scope]
    assert store.searches == [(scope, "question", [1.0, 0.0], 25)]
    assert store.closed == 1


async def test_retrieval_builds_context_only_from_ready_hits():
    providers, store, readiness = FakeProviderResolver(), Search(), Readiness()
    ready = hit()
    store.hits = [ready]
    readiness.ready_pairs = {(ready.document_id, ready.document_version_id)}
    context = await RetrieveContextUseCase(providers, readiness, lambda _: store).execute(
        RetrievalScope(uuid4(), uuid4()),
        "question",
        5,
    )
    assert "knowledge" in context.text and context.hits == [ready]


async def test_invalid_query_embedding_does_not_open_vector_store():
    providers, readiness = FakeProviderResolver(), Readiness()

    async def invalid(_):
        return [float("inf"), 0.0]

    providers.embedding.embed_query = invalid

    def forbidden(_):
        raise AssertionError("Invalid vectors must not be searched")

    with pytest.raises(CoreError) as error:
        await RetrieveContextUseCase(providers, readiness, forbidden).retrieve(
            RetrievalScope(uuid4(), uuid4()),
            "question",
            5,
        )
    assert error.value.code == "PROVIDER_INVALID_RESPONSE" and not readiness.calls


async def test_readiness_failure_closes_search_and_maps_error():
    providers, store, readiness = FakeProviderResolver(), Search(), Readiness()

    async def failed(*_):
        raise ConnectionError("database failure")

    readiness.filter_ready = failed
    with pytest.raises(CoreError) as error:
        await RetrieveContextUseCase(providers, readiness, lambda _: store).retrieve(
            RetrievalScope(uuid4(), uuid4()),
            "question",
            5,
        )
    assert error.value.code == "SEARCH_UNAVAILABLE" and store.closed == 1


@pytest.mark.parametrize("failure", [None, "timeout", "duplicate", "authentication"])
async def test_optional_rerank_preserves_scope_readiness_sources_and_fallback(failure):
    import asyncio
    from types import SimpleNamespace

    from raghub_core.domain.providers.contracts import RerankItem, RerankResult
    from raghub_core.domain.providers.errors import ProviderAuthenticationError
    from raghub_core.ports.rerank import RerankRuntime

    providers, store, readiness = FakeProviderResolver(), Search(), Readiness()
    scope = RetrievalScope(uuid4(), uuid4())
    first, second, stale = hit(), hit(), hit()
    store.hits = [stale, first, second]
    readiness.ready_pairs = {(c.document_id, c.document_version_id) for c in [first, second]}
    calls, scopes, statuses = [], [], []

    async def rerank(**kwargs):
        calls.append(kwargs)
        if failure == "timeout":
            await asyncio.sleep(1)
        if failure == "authentication":
            raise ProviderAuthenticationError()
        return RerankResult(
            [RerankItem(1, 0.9), RerankItem(1 if failure == "duplicate" else 0, 0.1)], "m", "p"
        )

    async def resolve(given_scope):
        scopes.append(given_scope)
        return RerankRuntime(SimpleNamespace(rerank=rerank), 40, 2, 0.1)

    use_case = RetrieveContextUseCase(
        providers,
        readiness,
        lambda _: store,
        SimpleNamespace(resolve_rerank=resolve),
        statuses.append,
    )
    context = await use_case.execute(scope, "question", 2)
    assert context.hits == ([second, first] if failure is None else [first, second])
    assert scopes == readiness.calls == providers.scopes == [scope]
    assert calls == [
        {"query": "question", "documents": [first.content, second.content], "top_n": 2}
    ]
    assert store.searches[0][-1] == 40 and store.closed == 1
    assert statuses == ["OK" if failure is None else "DEGRADED_REQUEST"]


async def test_optional_rerank_resolution_failure_uses_original_ready_order():
    from types import SimpleNamespace

    providers, store, readiness = FakeProviderResolver(), Search(), Readiness()
    ready = hit()
    store.hits = [ready]
    readiness.ready_pairs = {(ready.document_id, ready.document_version_id)}

    async def resolve(_):
        raise ConnectionError("Cannot resolve optional configuration")

    statuses = []
    use_case = RetrieveContextUseCase(
        providers,
        readiness,
        lambda _: store,
        SimpleNamespace(resolve_rerank=resolve),
        statuses.append,
    )
    assert await use_case.retrieve(RetrievalScope(uuid4(), uuid4()), "q", 1) == [ready]
    assert statuses == ["DEGRADED_RESOLUTION"]
