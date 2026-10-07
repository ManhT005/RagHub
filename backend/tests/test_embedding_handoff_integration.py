"""Real DB checkpoints and retry/resume; provider/storage/index are deterministic fakes."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from raghub_core.domain.ingestion.chunker import TextChunk
from raghub_core.domain.ingestion.models import IngestionDocument
from raghub_core.domain.providers.errors import ProviderRateLimitError
from raghub_core.domain.retrieval.models import RetrievalScope
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.infrastructure.embedding_execution import EmbeddingDeferred
from app.infrastructure.providers import ProviderResolverAdapter
from app.infrastructure.resumable_embedding import ResumableEmbedding
from app.modules.ai_providers.models import EmbeddingBatchCheckpoint, EmbeddingWorkItem
from app.modules.documents.models import DocumentVersion, IngestionJob
from app.workers import embedding_tasks
from tests.core.fakes import FakeObjectStorage
from tests.test_resumable_db_integration import seed

pytestmark = pytest.mark.integration


async def test_handoff_retry_and_process_restart_never_reparse_or_repeat_checkpoint(
    isolated_sessions, monkeypatch
):
    settings = Settings(
        _env_file=None,
        rag_embedding_speed_profile="custom",
        rag_embedding_batch_max_chunks=1,
        database_url=os.environ["RAGHUB_TEST_DATABASE_URL"],
    )
    storage = FakeObjectStorage()
    calls, published = [], []

    async def embed(texts):
        calls.append(texts[0])
        if texts == ["chunk 1"] and calls.count("chunk 1") == 1:
            error = ProviderRateLimitError()
            error.details["retry_after_seconds"] = 3
            raise error
        return [[float(texts[0].split()[-1])] * 384]

    provider = SimpleNamespace(embed_documents=embed)
    monkeypatch.setattr(embedding_tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(embedding_tasks, "MinioObjectStorage", lambda _: storage)
    enqueue = Mock()
    monkeypatch.setattr(embedding_tasks.process_work_item_batch, "delay", enqueue)
    monkeypatch.setattr(ProviderResolverAdapter, "resolve_embedding_version", AsyncMock())

    class Indexer:
        def __init__(self, **kwargs):
            pass

        def replace_document_version(self, **kwargs):
            published.append(kwargs)

        def close(self):
            pass

    monkeypatch.setattr("app.infrastructure.elasticsearch.chunks.ChunkIndexer", Indexer)
    async with isolated_sessions(expire_on_commit=False) as session:
        schema = await session.scalar(text("SELECT current_schema()"))
        monkeypatch.setattr(
            embedding_tasks,
            "create_async_engine",
            lambda url, **kwargs: create_async_engine(
                url, connect_args={"server_settings": {"search_path": schema}}, **kwargs
            ),
        )
        org, ws, index, version = await seed(session)
        version.status = "EMBEDDING"
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version.id)
        )
        job.stage, job.progress = "EMBEDDING", 65
        await session.commit()
        document = IngestionDocument(
            RetrievalScope(org.id, ws.id),
            version.document_id,
            version.id,
            version.storage_key,
            "guide.txt",
        )
        chunks = [
            TextChunk(uuid4(), i, f"chunk {i}", 2, "guide.txt", None, None, str(i))
            for i in range(3)
        ]
        runtime = SimpleNamespace(
            fingerprint=index.embedding_fingerprint,
            index_name=index.index_name,
            dimension=384,
            provider=provider,
            quota_scope=None,
        )
        ProviderResolverAdapter.resolve_embedding_version.return_value = runtime
        embeddings = ResumableEmbedding(session, storage, settings, defer_uploads=True)
        with pytest.raises(EmbeddingDeferred):
            await embeddings.execute(document, chunks, runtime)
        item_id = embeddings.identity(document, runtime)
        enqueue.assert_called_once_with(str(item_id))
        version_id = version.id

    # Each delivery uses a fresh session, as if the worker process restarted.
    async with isolated_sessions(expire_on_commit=False) as session:
        assert await embedding_tasks._run_delivery(str(item_id)) == (False, 0)
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        assert job.embedded_chunks == 1 and job.progress == 71 and job.stage == "EMBEDDING"
    async with isolated_sessions(expire_on_commit=False) as session:
        done, delay = await embedding_tasks._run_delivery(str(item_id))
        assert not done and delay == 3
        item = await session.get(EmbeddingWorkItem, item_id)
        assert item.state == "WAITING_QUOTA" and item.error_code == "PROVIDER_RATE_LIMIT"
        assert list(
            await session.scalars(
                select(EmbeddingBatchCheckpoint.batch_index).where(
                    EmbeddingBatchCheckpoint.work_item_id == item_id
                )
            )
        ) == [0]
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        assert job.embedded_chunks == 1 and job.progress == 71 and job.stage == "EMBEDDING"
    await asyncio.sleep(3.05)
    for expected_done in (False, True):
        async with isolated_sessions(expire_on_commit=False) as session:
            done, _ = await embedding_tasks._run_delivery(str(item_id))
            assert done == expected_done
    async with isolated_sessions() as session:
        version = await session.get(DocumentVersion, version_id)
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        assert version.status == job.stage == "READY" and job.progress == 100
        assert job.embedded_chunks == job.total_chunks == 3
        assert (await session.get(EmbeddingWorkItem, item_id)).state == "COMPLETED"
    assert calls == ["chunk 0", "chunk 1", "chunk 1", "chunk 2"]
    assert len(published) == 1
