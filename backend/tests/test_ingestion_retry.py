import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from celery.exceptions import Retry

from app.workers import tasks


def test_transient_failure_requests_retry_without_marking_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = tasks.IngestionError("INDEX_UNAVAILABLE", "index down", retryable=True)
    process = AsyncMock(side_effect=error)
    update = AsyncMock()
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(tasks, "_process_document_version", process)
    monkeypatch.setattr(tasks, "_update_job", update)
    monkeypatch.setattr(tasks.ingest_document_version, "retry", retry)
    with pytest.raises(Retry):
        tasks.ingest_document_version.run(str(uuid.uuid4()))
    assert update.await_args_list[-1].kwargs["code"] == "INDEX_UNAVAILABLE"
    assert update.await_args_list[-1].kwargs.get("failed") is None
    assert retry.call_args.kwargs["countdown"] == 2


def test_permanent_failure_is_recorded_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    error = tasks.IngestionError("INVALID_PDF", "broken", retryable=False)
    update = AsyncMock()
    retry = Mock()
    monkeypatch.setattr(tasks, "_process_document_version", AsyncMock(side_effect=error))
    monkeypatch.setattr(tasks, "_update_job", update)
    monkeypatch.setattr(tasks.ingest_document_version, "retry", retry)
    with pytest.raises(tasks.IngestionError):
        tasks.ingest_document_version.run(str(uuid.uuid4()))
    assert update.await_args_list[-1].kwargs["code"] == "INVALID_PDF"
    assert update.await_args_list[-1].kwargs["failed"] is True
    retry.assert_not_called()


def test_transient_failure_after_three_retries_is_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    error = tasks.IngestionError("STORAGE_UNAVAILABLE", "storage down", retryable=True)
    update = AsyncMock()
    retry = Mock()
    monkeypatch.setattr(tasks, "_process_document_version", AsyncMock(side_effect=error))
    monkeypatch.setattr(tasks, "_update_job", update)
    monkeypatch.setattr(tasks.ingest_document_version, "retry", retry)
    tasks.ingest_document_version.push_request(retries=3)
    try:
        with pytest.raises(tasks.IngestionError):
            tasks.ingest_document_version.run(str(uuid.uuid4()))
    finally:
        tasks.ingest_document_version.pop_request()
    assert update.await_args_list[-1].kwargs["attempts"] == 4
    assert update.await_args_list[-1].kwargs["failed"] is True
    retry.assert_not_called()
