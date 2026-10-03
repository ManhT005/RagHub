from uuid import uuid4

import pytest

from app.application.retrieval.retrieve_context import RetrieveContextUseCase
from app.core_domain.errors import CoreError
from app.core_domain.retrieval.models import RetrievalScope, RetrievedChunk

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
    assert store.searches == [(scope, "question", [1.0, 0.0], 15)]
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
    assert "knowledge" in context.text and context.hits == [ready.as_hit()]


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
