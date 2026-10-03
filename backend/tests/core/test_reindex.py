from uuid import uuid4

import pytest

from app.application.ingestion.build_document_index import BuildDocumentIndexUseCase
from app.application.ingestion.reindex_workspace import ReindexWorkspaceUseCase
from app.core_domain.ingestion.errors import IngestionError
from app.core_domain.ingestion.models import IngestionDocument
from app.core_domain.ingestion.parser import parse_document
from app.core_domain.ingestion.reindex import ReindexTarget
from app.core_domain.retrieval.models import RetrievalScope

from .fakes import FakeObjectStorage, FakeProviderResolver, FakeVectorStore


class Repository:
    def __init__(self):
        self.target = ReindexTarget(
            uuid4(), RetrievalScope(uuid4(), uuid4()), uuid4(), "QUEUED", True
        )
        self.documents = [IngestionDocument(self.target.scope, uuid4(), uuid4(), "key", "a.txt")]
        self.states = []
        self.progress = 8
        self.activated = False
        self.rollbacks = 0
        self.failures = []

    async def load(self, job_id):
        return self.target

    async def mark(self, job_id, status):
        self.states.append(status)

    async def latest_documents(self, target):
        return self.documents

    async def reset_progress(self, job_id, total):
        self.progress = 0
        self.total = total

    async def processed(self, job_id):
        self.progress += 1

    async def activate(self, target):
        self.activated = True
        return True

    async def fail(self, job_id, exc):
        self.failures.append(exc)

    async def rollback(self):
        self.rollbacks += 1


def rebuild():
    repository, storage = Repository(), FakeObjectStorage()
    storage.objects["key"] = b"knowledge"
    providers, store = FakeProviderResolver(), FakeVectorStore()
    use_case = ReindexWorkspaceUseCase(
        repository,
        BuildDocumentIndexUseCase(storage, parse_document),
        providers,
        lambda _: store,
    )
    return repository, providers, store, use_case


async def test_rebuild_reuses_document_indexing_and_resets_redelivery_progress():
    repository, providers, store, use_case = rebuild()
    await use_case.execute(repository.target.job_id)
    assert repository.states == ["RUNNING", "VALIDATING", "SWITCHING"]
    assert repository.progress == 1 and repository.activated
    assert providers.versions == [repository.target.index_version_id]
    assert store.indexes[0].scope == repository.target.scope and store.closed == 1


async def test_obsolete_target_does_not_build_or_activate():
    repository, providers, store, use_case = rebuild()
    old = repository.target
    repository.target = ReindexTarget(
        old.job_id, old.scope, old.index_version_id, old.status, False
    )
    await use_case.execute(old.job_id)
    assert repository.states == ["SUPERSEDED"]
    assert not providers.versions and not store.indexes and not repository.activated


@pytest.mark.parametrize("exhausted", [False, True])
async def test_rebuild_failure_keeps_active_index_and_obeys_retry_budget(exhausted):
    repository, _, store, use_case = rebuild()
    store.error = ConnectionError("offline")
    with pytest.raises(IngestionError):
        await use_case.execute(repository.target.job_id, fail_transient=exhausted)
    assert not repository.activated and store.closed == 1
    assert bool(repository.failures) == exhausted
    assert repository.rollbacks == int(not exhausted)


async def test_missing_document_prevents_index_activation():
    repository, _, store, use_case = rebuild()
    store.document_version_ids = lambda _: set()
    with pytest.raises(RuntimeError, match="missing"):
        await use_case.execute(repository.target.job_id)
    assert not repository.activated and repository.failures and store.closed == 1
