import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.delivery.workers.ingestion import _process_document_version
from app.infrastructure.task_queue.celery_app import (
    INGESTION_QUEUE,
    PROVIDER_QUEUE,
    RAG_WORKER_QUEUES,
    REINDEX_QUEUE,
    celery_app,
)
from app.modules.documents.schemas import DocumentResponse


def test_rag_hardware_profile_precedence_and_empty_env():
    # 1. Preset defaults apply when no overrides are given
    lite = Settings(_env_file=None, rag_hardware_profile="lite_cpu")
    assert lite.rag_worker_concurrency == 1
    assert lite.rag_retrieval_candidates == 15
    assert lite.rag_rerank_source_count == 12
    assert lite.rag_rerank_top_n == 5

    gpu = Settings(_env_file=None, rag_hardware_profile="gpu")
    assert gpu.rag_worker_concurrency == 2
    assert gpu.rag_retrieval_candidates == 40
    assert gpu.rag_rerank_source_count == 40
    assert gpu.rag_rerank_top_n == 8
    assert gpu.provider_pool_max_active_jobs_per_workspace == 2

    # 2. Empty string (from Compose ${VAR:-}) must not override preset
    gpu_with_empty = Settings(
        _env_file=None,
        rag_hardware_profile="gpu",
        rag_worker_concurrency="",  # type: ignore[arg-type]
        rag_retrieval_candidates="",  # type: ignore[arg-type]
        rag_rerank_source_count="",  # type: ignore[arg-type]
    )
    assert gpu_with_empty.rag_worker_concurrency == 2
    assert gpu_with_empty.rag_retrieval_candidates == 40
    assert gpu_with_empty.rag_rerank_source_count == 40

    # 3. Explicit non-empty value overrides preset
    gpu_override = Settings(
        _env_file=None,
        rag_hardware_profile="gpu",
        rag_worker_concurrency=1,
        rag_retrieval_candidates=50,
    )
    assert gpu_override.rag_worker_concurrency == 1
    assert gpu_override.rag_retrieval_candidates == 50


def test_worker_queue_topology_and_isolation():
    routes = celery_app.conf.task_routes

    # User-facing RAG workloads
    assert routes["documents.ingest_version"]["queue"] == INGESTION_QUEUE
    assert routes["embedding.process_work_item_batch"]["queue"] == "rag-embedding"
    assert routes["providers.reindex_workspace"]["queue"] == REINDEX_QUEUE

    # Dedicated provider workloads (never share slots with ingestion)
    assert routes["providers.bootstrap_health"]["queue"] == PROVIDER_QUEUE
    assert routes["providers.local_download"]["queue"] == PROVIDER_QUEUE
    assert routes["providers.ollama_pull"]["queue"] == PROVIDER_QUEUE

    # Verify RAG queues do not overlap with provider queue
    assert PROVIDER_QUEUE not in RAG_WORKER_QUEUES
    assert "celery" not in RAG_WORKER_QUEUES


from datetime import UTC, datetime


def test_document_response_waiting_reason():
    now = datetime.now(UTC)
    queued_doc = DocumentResponse(
        id=uuid.uuid4(),
        name="test.pdf",
        status="QUEUED",
        created_at=now,
        stage="QUEUED",
        waiting_reason="WAITING_FOR_WORKER",
    )
    assert queued_doc.stage == "QUEUED"
    assert queued_doc.waiting_reason == "WAITING_FOR_WORKER"

    ready_doc = DocumentResponse(
        id=uuid.uuid4(),
        name="ready.pdf",
        status="READY",
        created_at=now,
        stage="READY",
        waiting_reason=None,
    )
    assert ready_doc.stage == "READY"
    assert ready_doc.waiting_reason is None


from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_ingestion_returns_structured_result_when_lock_not_acquired():
    version_id = uuid.uuid4()
    with patch("app.delivery.workers.ingestion.create_async_engine") as mock_engine_factory:
        mock_engine = MagicMock()
        mock_conn = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_conn
        mock_cm.__aexit__.return_value = None
        mock_engine.connect.return_value = mock_cm
        mock_engine.dispose = AsyncMock()
        mock_engine_factory.return_value = mock_engine

        with patch("app.delivery.workers.ingestion.try_ingestion_lock") as mock_lock:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = False
            mock_ctx.__aexit__.return_value = None
            mock_lock.return_value = mock_ctx

            result = await _process_document_version(version_id)
            assert isinstance(result, dict)
            assert result["version_id"] == str(version_id)
            assert result["status"] == "SKIPPED"
            assert result["processed"] is False
            assert result["reason"] == "CONCURRENT_LOCK_HELD"
            assert "duration_ms" in result
