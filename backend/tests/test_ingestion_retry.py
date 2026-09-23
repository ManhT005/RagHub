import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from celery.exceptions import Retry

from app.workers import tasks


@pytest.mark.parametrize(
    "retryable,retries,expected_retry", [(True, 0, True), (False, 0, False), (True, 3, False)]
)
def test_celery_retry_policy(
    monkeypatch: pytest.MonkeyPatch, retryable: bool, retries: int, expected_retry: bool
) -> None:
    error = tasks.IngestionError(
        "INDEX_UNAVAILABLE" if retryable else "INVALID_PDF", "private details", retryable=retryable
    )
    process = AsyncMock(side_effect=error)
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(tasks, "_process_document_version", process)
    monkeypatch.setattr(tasks.ingest_document_version, "retry", retry)
    tasks.ingest_document_version.push_request(retries=retries)
    try:
        with pytest.raises(Retry if expected_retry else tasks.IngestionError):
            tasks.ingest_document_version.run(str(uuid.uuid4()))
    finally:
        tasks.ingest_document_version.pop_request()
    if expected_retry:
        assert retry.call_args.kwargs["countdown"] == 2
    else:
        retry.assert_not_called()


@pytest.mark.parametrize("status", ["READY", "FAILED"])
async def test_terminal_redelivery_does_not_mutate_metrics(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    version = SimpleNamespace(status=status)
    job = SimpleNamespace(progress=100)
    session = SimpleNamespace(
        get=AsyncMock(return_value=version), commit=AsyncMock(), scalar=AsyncMock(return_value=job)
    )
    pipeline = AsyncMock()
    monkeypatch.setattr(tasks, "_run_pipeline", pipeline)
    await tasks._run_attempt(session, uuid.uuid4(), retries=0, max_retries=3)
    session.commit.assert_not_awaited()
    if status == "READY":
        session.scalar.assert_awaited_once()
    else:
        session.scalar.assert_not_awaited()
    pipeline.assert_not_awaited()


async def test_incomplete_ready_redelivery_resumes_indexing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = SimpleNamespace(id=uuid.uuid4(), document_id=uuid.uuid4(), status="READY")
    document = SimpleNamespace(status="READY", deleted_at=None)
    job = SimpleNamespace(attempts=0, stage="READY", progress=90)
    session = SimpleNamespace(
        get=AsyncMock(side_effect=[version, document]),
        scalar=AsyncMock(return_value=job),
        commit=AsyncMock(),
    )
    pipeline = AsyncMock()
    monkeypatch.setattr(tasks, "_run_pipeline", pipeline)

    await tasks._run_attempt(session, version.id, retries=0, max_retries=3)

    assert job.attempts == 1
    assert document.status == version.status == job.stage == "PARSING"
    pipeline.assert_awaited_once_with(session, document, version, job)


async def test_pipeline_marks_version_ready_before_writing_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = SimpleNamespace(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), workspace_id=uuid.uuid4(), storage_key="key"
    )
    document = SimpleNamespace(id=uuid.uuid4(), name="a.txt", status="PARSING")
    job = SimpleNamespace(
        stage="PARSING", progress=20, error_code="old", error_message="old", error_details={}
    )
    session = SimpleNamespace(commit=AsyncMock())
    observed: list[tuple[str, str, str, int]] = []

    class Indexer:
        def __init__(self, _settings: object) -> None:
            pass

        def replace_document_version(self, **_kwargs: object) -> None:
            observed.append((document.status, version.status, job.stage, job.progress))

        def delete_document_version(self, _version_id: uuid.UUID) -> None:
            raise AssertionError("cleanup is only for failed indexing")

        def close(self) -> None:
            pass

    storage = SimpleNamespace(get=lambda _key: b"text")
    monkeypatch.setattr(tasks, "MinioObjectStorage", lambda _settings: storage)
    monkeypatch.setattr(tasks, "parse_document", lambda _content, _name: [object()])
    monkeypatch.setattr(tasks, "chunk_sections", lambda _sections, _version_id: [object()])
    monkeypatch.setattr(tasks, "embed_chunks", lambda _chunks: {})
    monkeypatch.setattr(tasks, "ChunkIndexer", Indexer)

    await tasks._run_pipeline(session, document, version, job)

    assert observed == [("INDEXING", "READY", "INDEXING", 90)]
    assert document.status == version.status == job.stage == "READY"
    assert job.progress == 100


@pytest.mark.parametrize(
    "retryable,retries,failed", [(True, 0, False), (True, 3, True), (False, 0, True)]
)
async def test_attempt_records_failure_before_leaving_lock(
    monkeypatch: pytest.MonkeyPatch, retryable: bool, retries: int, failed: bool
) -> None:
    version = SimpleNamespace(id=uuid.uuid4(), document_id=uuid.uuid4(), status="QUEUED")
    document = SimpleNamespace(status="QUEUED", deleted_at=None)
    job = SimpleNamespace(attempts=retries, stage="QUEUED")
    session = SimpleNamespace(
        get=AsyncMock(side_effect=[version, document]),
        scalar=AsyncMock(return_value=job),
        commit=AsyncMock(),
    )
    error = tasks.IngestionError("INDEX_UNAVAILABLE", "private details", retryable=retryable)
    monkeypatch.setattr(tasks, "_run_pipeline", AsyncMock(side_effect=error))
    record = AsyncMock()
    monkeypatch.setattr(tasks, "_record_failure", record)
    with pytest.raises(tasks.IngestionError):
        await tasks._run_attempt(session, version.id, retries=retries, max_retries=3)
    assert job.attempts == retries + 1
    assert job.stage == version.status == document.status == "PARSING"
    record.assert_awaited_once_with(session, version.id, error, failed=failed)
