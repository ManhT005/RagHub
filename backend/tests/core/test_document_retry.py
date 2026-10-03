from dataclasses import replace
from uuid import uuid4

import pytest

from app.application.documents.retry_document import RetryDocumentUseCase
from raghub_core.domain.documents.upload import RetryDocumentState
from raghub_core.domain.errors import CoreError
from raghub_core.domain.retrieval.models import RetrievalScope

from .fakes import FakeTaskQueue, FakeUploadRepository


class Repository(FakeUploadRepository):
    def __init__(self, status="FAILED", error_code="INDEX_UNAVAILABLE"):
        super().__init__()
        self.state = RetryDocumentState(replace(self.receipt, status=status), error_code)
        self.locked = True
        self.resets = []
        self.scopes = []

    async def load_for_retry(self, scope, version_id):
        self.scopes.append(scope)
        return self.state

    async def try_retry_lock(self, version_id):
        return self.locked

    async def reset(self, version_id):
        self.resets.append(version_id)
        return self.receipt


@pytest.mark.parametrize("reindex", [False, True])
async def test_retry_and_reindex_keep_version_and_commit_before_queue(reindex):
    repository = Repository("READY" if reindex else "FAILED")
    queue = FakeTaskQueue()
    scope = RetrievalScope(uuid4(), uuid4())
    result = await RetryDocumentUseCase(repository, queue).execute(
        scope,
        repository.receipt.document_version_id,
        reindex=reindex,
    )
    assert result == repository.receipt and repository.resets == queue.ingestion
    assert repository.commits == 1 and repository.scopes == [scope]


@pytest.mark.parametrize("permanent", [False, True])
async def test_permanent_failure_or_active_worker_lock_prevents_retry(permanent):
    repository, queue = Repository(), FakeTaskQueue()
    if permanent:
        repository.state = replace(repository.state, error_code="INVALID_PDF")
    else:
        repository.locked = False
    with pytest.raises(CoreError) as error:
        await RetryDocumentUseCase(repository, queue).execute(
            RetrievalScope(uuid4(), uuid4()),
            repository.receipt.document_version_id,
        )
    assert error.value.code == ("DOCUMENT_NOT_RETRYABLE" if permanent else "INGESTION_IN_PROGRESS")
    assert not queue.ingestion and not repository.resets and not repository.commits


async def test_queue_failure_is_recorded_for_the_same_version():
    repository, queue = Repository(), FakeTaskQueue()
    queue.error = ConnectionError("offline")
    with pytest.raises(CoreError) as error:
        await RetryDocumentUseCase(repository, queue).execute(
            RetrievalScope(uuid4(), uuid4()),
            repository.receipt.document_version_id,
        )
    assert error.value.code == "QUEUE_UNAVAILABLE" and repository.commits == 2
    assert repository.failures[0][0] == repository.receipt.document_version_id
