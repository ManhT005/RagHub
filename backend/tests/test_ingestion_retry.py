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
    session = SimpleNamespace(
        get=AsyncMock(return_value=version), commit=AsyncMock(), scalar=AsyncMock()
    )
    pipeline = AsyncMock()
    monkeypatch.setattr(tasks, "_run_pipeline", pipeline)
    await tasks._run_attempt(session, uuid.uuid4(), retries=0, max_retries=3)
    session.commit.assert_not_awaited()
    session.scalar.assert_not_awaited()
    pipeline.assert_not_awaited()


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
