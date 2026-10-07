import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from raghub_core.domain.providers.errors import ProviderRateLimitError, ProviderTimeoutError

from app.core.config import Settings
from app.delivery.workers import ingestion
from app.infrastructure.embedding_execution import EmbeddingDeferred, resolve_policy
from app.infrastructure.ingestion_progress import advance_progress
from app.infrastructure.persistence.ingestion import IngestionRepositoryAdapter, _set_stage
from app.modules.ai_providers.service import config_fingerprint_v2, embedding_fingerprint
from app.modules.documents.schemas import DocumentResponse
from app.modules.documents.service import attach_work_state
from app.workers import embedding_tasks
from tests.test_embedding_schedule import FakeRepo, _manifest, _processor


@pytest.mark.parametrize("profile,expected", [("conservative", 1), ("balanced", 2), ("fast", 4)])
@pytest.mark.parametrize(
    "provider", ["OPENAI_COMPATIBLE", "GOOGLE_GEMINI", "LOCAL_SENTENCE_TRANSFORMER"]
)
async def test_bounded_parallel_policy_and_vector_order(profile, expected, provider):
    policy = resolve_policy(
        Settings(_env_file=None), provider, workspace_options={"profile": profile}
    )
    repo = FakeRepo()
    item = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        workspace_id=uuid4(),
        manifest_key="manifest",
        total_chunks=8,
        embedded_chunks=0,
        state="QUEUED",
    )
    repo.items[item.id] = item
    processor, blobs, calls = _processor(repo, max_chunks=1)
    processor.max_inflight = policy.max_inflight_requests
    blobs["manifest"] = _manifest(8)
    inflight = peak = 0

    async def embed(texts):
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        try:
            # Different durations force out-of-order completion.
            index = int(texts[0].split()[-1])
            await asyncio.sleep(0.003 * (4 - index % 4))
            return [[float(index), 0.0]]
        finally:
            inflight -= 1

    ordered = []
    processor.embed_texts = embed
    processor.finalize = AsyncMock(side_effect=lambda _, vectors: ordered.extend(vectors))
    while not (await processor.process_one(item.id)).done:
        pass
    assert peak == (1 if provider == "LOCAL_SENTENCE_TRANSFORMER" else expected)
    assert ordered == [[float(i), 0.0] for i in range(8)]
    assert len(repo.checkpoints[item.id]) == 8 and item.embedded_chunks == 8


async def test_successful_parallel_siblings_survive_rate_limit_and_resume():
    repo = FakeRepo()
    item = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        workspace_id=uuid4(),
        manifest_key="manifest",
        total_chunks=3,
        embedded_chunks=0,
        state="QUEUED",
    )
    repo.items[item.id] = item
    processor, blobs, _ = _processor(repo, max_chunks=1)
    processor.max_inflight = 3
    blobs["manifest"] = _manifest(3)
    calls = []

    async def embed(texts):
        calls.append(texts[0])
        await asyncio.sleep(0.005)
        if texts == ["chunk 1"] and calls.count("chunk 1") == 1:
            error = ProviderRateLimitError()
            error.details["retry_after_seconds"] = 3
            raise error
        return [[float(texts[0].split()[-1]), 0.0]]

    processor.embed_texts = embed
    with pytest.raises(ProviderRateLimitError):
        await processor.process_one(item.id)
    assert set(repo.checkpoints[item.id]) == {0, 2}
    assert item.embedded_chunks == 2
    assert (await processor.process_one(item.id)).done
    assert calls.count("chunk 0") == calls.count("chunk 2") == 1
    assert calls.count("chunk 1") == 2


def test_policy_precedence_caps_and_empty_env():
    settings = Settings(
        _env_file=None,
        rag_embedding_batch_max_chunks="",
        rag_embedding_batch_target_tokens="",
        rag_embedding_max_inflight_requests="",
        rag_embedding_max_inflight_hard_cap=2,
    )
    assert (
        resolve_policy(
            settings, "OPENAI_COMPATIBLE", workspace_options={"profile": "fast"}
        ).max_inflight_requests
        == 2
    )
    policy = resolve_policy(
        settings, "OPENAI_COMPATIBLE", {"max_inflight_requests": 1}, {"profile": "fast"}
    )
    assert policy.max_inflight_requests == 1 and policy.limited_by == "provider"
    assert (
        resolve_policy(
            settings, "OLLAMA", workspace_options={"profile": "fast"}
        ).max_inflight_requests
        == 1
    )


def test_execution_options_do_not_change_either_fingerprint():
    config = SimpleNamespace(
        id=uuid4(),
        provider_type="OPENAI_COMPATIBLE",
        base_url="https://api.example.com/v1",
        model="embedding",
        dimension=2,
        config_json={"task_type": "retrieval"},
    )
    legacy, v2 = embedding_fingerprint(config), config_fingerprint_v2(config)
    config.config_json.update(
        embedding_speed_profile="fast",
        max_inflight_requests=4,
        max_batch_tokens=35000,
        retry_delay_seconds=3,
    )
    assert embedding_fingerprint(config) == legacy and config_fingerprint_v2(config) == v2
    config.model = "other-model"
    assert config_fingerprint_v2(config) != v2


async def test_resume_begin_and_stage_updates_preserve_embedding_progress():
    document = SimpleNamespace(status="EMBEDDING")
    version = SimpleNamespace(status="EMBEDDING")
    job = SimpleNamespace(stage="EMBEDDING", progress=77, attempts=1, embedded_chunks=34)
    session = SimpleNamespace(commit=AsyncMock())
    repo = IngestionRepositoryAdapter(session, document=document, version=version, job=job)
    await repo.begin(uuid4())
    await _set_stage(session, document, version, job, "CHUNKING", 45)
    assert job.stage == version.status == document.status == "EMBEDDING"
    assert job.progress == 77 and job.embedded_chunks == 34
    assert advance_progress(65, 58) == 65


async def test_parent_redelivery_uses_manifest_without_parsing(monkeypatch):
    item = SimpleNamespace(id=uuid4(), state="QUEUED")
    session = SimpleNamespace(scalar=AsyncMock(return_value=item))
    enqueue = Mock()
    monkeypatch.setattr(embedding_tasks.process_work_item_batch, "delay", enqueue)
    monkeypatch.setattr(
        ingestion, "_make_container", Mock(side_effect=AssertionError("Must not parse"))
    )
    with pytest.raises(EmbeddingDeferred):
        await ingestion._run_pipeline(
            session, None, SimpleNamespace(id=uuid4()), SimpleNamespace(stage="EMBEDDING")
        )
    enqueue.assert_called_once_with(str(item.id))


@pytest.mark.parametrize(
    "error,reason,state,delay",
    [
        (ProviderRateLimitError(), "PROVIDER_RATE_LIMIT", "WAITING_QUOTA", 3),
        (ProviderTimeoutError(), "PROVIDER_TIMEOUT_RETRY", "RETRYING", 10),
    ],
)
async def test_embedding_worker_persists_retry_after_without_parent_retry(
    monkeypatch, error, reason, state, delay
):
    error.details["retry_after_seconds"] = delay
    item = SimpleNamespace(
        id=uuid4(),
        state="QUEUED",
        available_at=None,
        execution_config={},
        document_version_id=None,
        embedded_chunks=0,
    )
    session = SimpleNamespace(get=AsyncMock(return_value=item), commit=AsyncMock())
    monkeypatch.setattr(embedding_tasks, "_process_one_batch", AsyncMock(side_effect=error))
    before = datetime.now(UTC)
    done, wait = await embedding_tasks._run_locked(session, item.id)
    assert not done and wait == delay
    assert item.state == state and item.error_code == reason
    assert before + timedelta(seconds=delay) <= item.available_at
    assert item.execution_config["retry_count"] == 1


def test_api_wait_state_keeps_completed_chunks_and_progress():
    response = DocumentResponse(
        id=uuid4(),
        name="a.pdf",
        status="EMBEDDING",
        stage="EMBEDDING",
        progress=77,
        created_at=datetime.now(UTC),
    )
    retry = datetime.now(UTC) + timedelta(seconds=3)
    job = SimpleNamespace(stage="EMBEDDING", embedded_chunks=34, total_chunks=49)
    item = SimpleNamespace(
        state="WAITING_QUOTA",
        embedded_chunks=34,
        total_chunks=49,
        error_code="PROVIDER_RATE_LIMIT",
        available_at=retry,
    )
    attach_work_state(response, job, item)
    assert response.progress == 77 and response.embedded_chunks == 34
    assert response.work_state == "WAITING_QUOTA" and response.retry_at == retry
    assert response.waiting_reason == "PROVIDER_RATE_LIMIT"


async def test_retry_budget_is_bounded_per_failed_batch(monkeypatch):
    item = SimpleNamespace(
        id=uuid4(),
        state="QUEUED",
        available_at=None,
        embedded_chunks=0,
        execution_config={"retry_max_attempts": 2},
        document_version_id=None,
    )
    session = SimpleNamespace(get=AsyncMock(return_value=item), commit=AsyncMock())
    fail = AsyncMock()
    monkeypatch.setattr(embedding_tasks.WorkItemRepository, "fail", fail)
    errors = []
    for batch in (0, 1, 0):
        error = ProviderRateLimitError()
        error.embedding_batch_index = batch
        errors.append(error)
    monkeypatch.setattr(embedding_tasks, "_process_one_batch", AsyncMock(side_effect=errors))
    assert not (await embedding_tasks._run_locked(session, item.id))[0]
    item.available_at = None
    assert not (await embedding_tasks._run_locked(session, item.id))[0]
    item.available_at = None
    with pytest.raises(ProviderRateLimitError):
        await embedding_tasks._run_locked(session, item.id)
    fail.assert_awaited_once()
    assert item.execution_config["batch_retry_counts"] == {"0": 2, "1": 1}


async def test_current_hard_caps_reject_large_persisted_batches_before_provider():
    repo = FakeRepo()
    item = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        workspace_id=uuid4(),
        manifest_key="manifest",
        total_chunks=3,
        embedded_chunks=0,
        state="QUEUED",
    )
    repo.items[item.id] = item
    processor, blobs, calls = _processor(repo, max_chunks=3)
    processor.batch_hard_caps = (2, 1000)
    blobs["manifest"] = _manifest(3)
    with pytest.raises(ValueError, match="hard caps"):
        await processor.process_one(item.id)
    assert calls["embed"] == 0 and not repo.checkpoints
