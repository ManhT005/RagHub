from uuid import uuid4

import pytest

from raghub_core.application.documents.upload_document import UploadDocumentUseCase
from raghub_core.application.ingestion.build_document_index import BuildDocumentIndexUseCase
from raghub_core.application.ingestion.run_ingestion import RunIngestionUseCase
from raghub_core.domain.documents.upload import UploadDocumentCommand
from raghub_core.domain.errors import CoreError
from raghub_core.domain.ingestion.errors import IngestionError
from raghub_core.domain.ingestion.models import IngestionAttempt, IngestionDocument
from raghub_core.domain.ingestion.parser import parse_document
from raghub_core.domain.providers.errors import ProviderTimeoutError
from raghub_core.domain.retrieval.models import RetrievalScope

from .fakes import (
    FakeObjectStorage,
    FakeProviderResolver,
    FakeTaskQueue,
    FakeUploadRepository,
    FakeVectorStore,
)


class Repository:
    def __init__(self, document):
        self.attempt = IngestionAttempt(document, "QUEUED", 0)
        self.stages = []
        self.failures = []

    async def load(self, version_id):
        return self.attempt

    async def begin(self, version_id):
        self.stages.append(("PARSING", 20))

    async def set_stage(self, version_id, stage, progress):
        self.stages.append((stage, progress))

    async def expose_version(self, version_id):
        self.stages.append(("VERSION_READY", 90))

    async def complete(self, version_id):
        self.stages.append(("READY", 100))

    async def record_failure(self, version_id, error, *, failed):
        self.failures.append((error.code, failed))


def pipeline(content=b"# Guide\n\nKnowledge"):
    storage, providers, store = FakeObjectStorage(), FakeProviderResolver(), FakeVectorStore()
    document = IngestionDocument(RetrievalScope(uuid4(), uuid4()), uuid4(), uuid4(), "key", "a.md")
    storage.objects["key"] = content
    repository = Repository(document)
    builder = BuildDocumentIndexUseCase(storage, parse_document)
    use_case = RunIngestionUseCase(repository, builder, providers, lambda _: store)
    return document, repository, providers, store, use_case


async def test_pipeline_runs_without_celery_and_preserves_stage_order():
    document, repository, providers, store, use_case = pipeline()
    result = await use_case.execute(document.version_id)
    assert result.processed and result.status == "READY"
    assert repository.stages == [
        ("PARSING", 20),
        ("CHUNKING", 45),
        ("EMBEDDING", 65),
        ("INDEXING", 85),
        ("VERSION_READY", 90),
        ("READY", 100),
    ]
    assert store.indexes[0].scope == document.scope
    assert providers.scopes == [document.scope]
    assert store.closed == 1


@pytest.mark.parametrize("status,progress", [("READY", 100), ("FAILED", 0)])
async def test_terminal_redelivery_does_not_repeat_work(status, progress):
    document, repository, providers, store, use_case = pipeline()
    repository.attempt = IngestionAttempt(None, status, progress)
    assert not (await use_case.execute(document.version_id)).processed
    assert not repository.stages and not providers.scopes and not store.indexes


async def test_nonterminal_attempt_requires_metadata_before_starting_work():
    document, repository, providers, _, use_case = pipeline()
    repository.attempt = IngestionAttempt(None, "QUEUED", 0)
    with pytest.raises(ValueError, match="metadata"):
        await use_case.execute(document.version_id)
    assert not repository.stages and not providers.scopes


async def test_partial_ready_resumes_and_index_failure_cleans_up_before_retry():
    document, repository, _, store, use_case = pipeline()
    repository.attempt = IngestionAttempt(document, "READY", 90)
    store.error = ConnectionError("offline")
    with pytest.raises(IngestionError) as error:
        await use_case.execute(document.version_id)
    assert error.value.retryable
    assert repository.failures == [("INDEX_UNAVAILABLE", False)]
    assert store.deleted == [document.version_id] and store.closed == 1


@pytest.mark.parametrize("retries,failed", [(0, False), (3, True)])
async def test_embedding_timeout_obeys_retry_budget(retries, failed):
    document, repository, providers, store, use_case = pipeline()
    providers.embedding.error = ProviderTimeoutError()
    with pytest.raises(IngestionError):
        await use_case.execute(document.version_id, retries=retries)
    assert repository.failures == [("EMBEDDING_FAILED", failed)]
    assert not store.indexes


@pytest.mark.parametrize("vectors", [[], [[1.0]], [[float("nan"), 0.0]]])
async def test_invalid_embedding_never_reaches_index(vectors):
    document, repository, providers, store, use_case = pipeline()
    providers.embedding.vectors = vectors
    with pytest.raises(IngestionError):
        await use_case.execute(document.version_id)
    assert repository.failures == [("EMBEDDING_FAILED", True)] and not store.indexes


async def test_upload_stores_checksum_and_queues_only_after_commit():
    storage, queue, repository = FakeObjectStorage(), FakeTaskQueue(), FakeUploadRepository()
    use_case = UploadDocumentUseCase(repository, storage, queue)
    command = UploadDocumentCommand(uuid4(), uuid4(), "../../guide.txt", "text/plain", b"knowledge")
    receipt = await use_case.execute(command)
    assert queue.ingestion == [receipt.document_version_id] and repository.commits == 1
    assert repository.uploads[0]["filename"] == "guide.txt"
    assert len(repository.uploads[0]["checksum"]) == 64
    assert list(storage.objects.values()) == [b"knowledge"]


async def test_upload_rolls_back_and_removes_orphan_on_database_error():
    storage, queue, repository = FakeObjectStorage(), FakeTaskQueue(), FakeUploadRepository()
    repository.error = RuntimeError("database failure")
    with pytest.raises(RuntimeError):
        await UploadDocumentUseCase(repository, storage, queue).execute(
            UploadDocumentCommand(uuid4(), uuid4(), "a.txt", "text/plain", b"knowledge")
        )
    assert repository.rollbacks == 1 and storage.removed and not storage.objects
    assert not queue.ingestion


async def test_queue_failure_keeps_original_and_records_retryable_failure():
    storage, queue, repository = FakeObjectStorage(), FakeTaskQueue(), FakeUploadRepository()
    queue.error = ConnectionError("broker failure")
    with pytest.raises(CoreError) as error:
        await UploadDocumentUseCase(repository, storage, queue).execute(
            UploadDocumentCommand(uuid4(), uuid4(), "a.txt", "text/plain", b"knowledge")
        )
    assert error.value.code == "QUEUE_UNAVAILABLE" and storage.objects
    assert repository.failures[0][0] == repository.receipt.document_version_id
