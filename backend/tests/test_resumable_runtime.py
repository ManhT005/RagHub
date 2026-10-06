from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from raghub_core.domain.ingestion.chunker import chunk_sections
from raghub_core.domain.ingestion.models import IngestionDocument
from raghub_core.domain.ingestion.parser import ParsedSection
from raghub_core.domain.retrieval.models import RetrievalScope
from raghub_core.ports.provider_resolver import EmbeddingRuntime

from app.core.config import Settings
from app.infrastructure.embedding_cache import EmbeddingCache
from app.infrastructure.resumable_embedding import ResumableEmbedding
from tests.core.fakes import FakeObjectStorage
from tests.test_embedding_schedule import FakeRepo


async def test_canonical_resume_skips_durable_batches_and_waits_for_index_completion():
    storage = FakeObjectStorage()
    document = IngestionDocument(
        RetrievalScope(uuid4(), uuid4()), uuid4(), uuid4(), "file", "a.txt"
    )
    chunks = chunk_sections([ParsedSection("word " * 12000, "a.txt", 0)], document.version_id)
    provider = SimpleNamespace(embed_documents=AsyncMock())
    runtime = EmbeddingRuntime(provider, "new-index", 2, fingerprint="semantic-fp")
    item_id = ResumableEmbedding.identity(document, runtime)
    repo = FakeRepo()

    async def create(**kwargs):
        item = SimpleNamespace(**kwargs, id=item_id, state="QUEUED", embedded_chunks=0)
        repo.items[item_id] = item
        return item

    repo.create = create
    session = SimpleNamespace(
        get=AsyncMock(side_effect=lambda model, key: repo.items.get(key)), commit=AsyncMock()
    )
    adapter = ResumableEmbedding(session, storage, Settings())
    adapter.repository = repo
    calls = []

    async def interrupted(texts):
        calls.append(len(texts))
        if len(calls) == 2:
            raise ConnectionError("worker interrupted")
        return [[1.0, 0.0] for _ in texts]

    provider.embed_documents.side_effect = interrupted
    with pytest.raises(ConnectionError):
        await adapter.execute(document, chunks, runtime)
    assert repo.checkpoints[item_id]
    first = calls[0]
    vectors = await adapter.execute(document, chunks, runtime)
    assert len(vectors) == len(chunks)
    assert sum(calls) - calls[1] == len(chunks)
    assert calls[0] == first <= 24
    assert repo.items[item_id].state == "EMBEDDED"
    await adapter.complete(document, runtime)
    assert repo.items[item_id].state == "COMPLETED"


async def test_cache_deduplicates_content_and_never_crosses_fingerprints():
    storage = FakeObjectStorage()
    organization_id = uuid4()
    embed = AsyncMock(side_effect=lambda texts: [[1.0, 0.0] for _ in texts])
    first = EmbeddingCache(storage, organization_id, "fp-a", 2)
    assert len(await first.embed(["same", "same"], embed)) == 2
    embed.assert_awaited_once_with(["same"])
    await first.embed(["same"], embed)
    assert embed.await_count == 1
    await EmbeddingCache(storage, organization_id, "fp-b", 2).embed(["same"], embed)
    assert embed.await_count == 2


async def test_cache_records_actual_saved_embedding_calls_and_tokens():
    from app.infrastructure.telemetry.adapter import InMemoryTelemetry

    telemetry = InMemoryTelemetry()
    storage = FakeObjectStorage()
    embed = AsyncMock(side_effect=lambda texts: [[1.0, 0.0] for _ in texts])
    cache = EmbeddingCache(storage, uuid4(), "fp", 2, telemetry=telemetry)
    await cache.embed(["a useful fact"], embed)
    await cache.embed(["a useful fact", "a useful fact"], embed)
    assert embed.await_count == 1
    assert ("embedding_provider_calls_saved", {}, 1) in telemetry.counters
    assert any(
        name == "embedding_tokens_saved" and value > 0 for name, labels, value in telemetry.counters
    )


async def test_checkpoint_write_outage_resumes_orphan_vectors_without_another_provider_call():
    from raghub_core.domain.ingestion.errors import IngestionError

    class LostResponseStorage(FakeObjectStorage):
        failed = False

        async def put(self, key, blob, content_type):
            await super().put(key, blob, content_type)
            if "/embedding-batches/" in key and not self.failed:
                self.failed = True
                raise ConnectionError("response lost after persistence")

    storage = LostResponseStorage()
    document = IngestionDocument(
        RetrievalScope(uuid4(), uuid4()), uuid4(), uuid4(), "file", "a.txt"
    )
    chunks = chunk_sections([ParsedSection("A useful fact.", "a.txt", 0)], document.version_id)
    provider = SimpleNamespace(embed_documents=AsyncMock(return_value=[[1.0, 0.0]]))
    runtime = EmbeddingRuntime(provider, "index", 2, fingerprint="fp")
    repo = FakeRepo()

    async def create(**kwargs):
        item = SimpleNamespace(
            **kwargs,
            id=ResumableEmbedding.identity(document, runtime),
            state="QUEUED",
            embedded_chunks=0,
        )
        repo.items[item.id] = item
        return item

    repo.create = create
    session = SimpleNamespace(
        get=AsyncMock(side_effect=lambda model, key: repo.items.get(key)), commit=AsyncMock()
    )
    adapter = ResumableEmbedding(session, storage, Settings())
    adapter.repository = repo
    with pytest.raises(IngestionError) as error:
        await adapter.execute(document, chunks, runtime)
    assert error.value.retryable and error.value.code == "STORAGE_UNAVAILABLE"
    assert await adapter.execute(document, chunks, runtime) == [[1.0, 0.0]]
    assert provider.embed_documents.await_count == 1
