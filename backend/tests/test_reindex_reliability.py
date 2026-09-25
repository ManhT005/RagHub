import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.ai_providers.enums import ReindexJobStatus
from app.modules.ai_providers.service import ProviderConfigService
from app.workers.reindex_tasks import _has_all_document_versions, _is_current_target


def test_only_latest_pending_index_is_allowed_to_activate() -> None:
    older = SimpleNamespace(id=uuid.uuid4())
    newer = SimpleNamespace(id=uuid.uuid4())
    workspace = SimpleNamespace(pending_embedding_index_version_id=newer.id)

    assert not _is_current_target(workspace, older)  # type: ignore[arg-type]
    assert _is_current_target(workspace, newer)  # type: ignore[arg-type]


def test_validation_requires_every_expected_document_version() -> None:
    expected = {uuid.uuid4(), uuid.uuid4(), uuid.uuid4()}
    indexed = set(expected)

    assert _has_all_document_versions(expected, indexed)
    indexed.remove(next(iter(expected)))
    assert not _has_all_document_versions(expected, indexed)


async def test_enqueue_failure_is_persisted_as_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = SimpleNamespace(id=uuid.uuid4(), status=ReindexJobStatus.QUEUED)
    session = SimpleNamespace(commit=AsyncMock())
    service = object.__new__(ProviderConfigService)
    service.session = session

    class UnavailableTask:
        @staticmethod
        def delay(_job_id: str) -> None:
            raise ConnectionError("broker unavailable")

    monkeypatch.setattr("app.workers.reindex_tasks.reindex_workspace", UnavailableTask)

    await service._enqueue_reindex(job)  # type: ignore[arg-type]

    assert job.status == ReindexJobStatus.QUEUE_FAILED
    assert job.error_code == "REINDEX_QUEUE_UNAVAILABLE"
    session.commit.assert_awaited_once()
