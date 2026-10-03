from datetime import UTC, datetime
from uuid import uuid4

from app.core_domain.documents.upload import UploadReceipt
from app.core_domain.providers.contracts import ChatStreamDelta, EmbeddingMetadata
from app.ports.provider_resolver import ChatRuntime, EmbeddingRuntime


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.removed: list[str] = []

    def put(self, key: str, content: bytes, content_type: str) -> None:
        self.objects[key] = content

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def remove(self, key: str) -> None:
        self.removed.append(key)
        self.objects.pop(key, None)


class FakeTaskQueue:
    def __init__(self) -> None:
        self.ingestion = []
        self.reindex = []
        self.error = None

    def enqueue_ingestion(self, version_id) -> None:
        if self.error:
            raise self.error
        self.ingestion.append(version_id)

    def enqueue_reindex(self, job_id) -> None:
        if self.error:
            raise self.error
        self.reindex.append(job_id)


class FakeEmbeddingProvider:
    metadata = EmbeddingMetadata("fake", "model", 2)

    def __init__(self) -> None:
        self.calls = []
        self.error = None
        self.vectors = None

    async def embed_documents(self, texts):
        self.calls.append(texts)
        if self.error:
            raise self.error
        return self.vectors if self.vectors is not None else [[1.0, 0.0] for _ in texts]

    async def embed_query(self, text):
        self.calls.append(text)
        return [1.0, 0.0]


class FakeChatProvider:
    provider_name = "fake"
    model = "model"

    def __init__(self) -> None:
        self.deltas = [ChatStreamDelta(text="answer")]
        self.error = None
        self.calls = []

    async def stream_chat(self, messages, options):
        self.calls.append((messages, options))
        for delta in self.deltas:
            yield delta
        if self.error:
            raise self.error


class FakeProviderResolver:
    def __init__(self) -> None:
        self.embedding = FakeEmbeddingProvider()
        self.chat = FakeChatProvider()
        self.scopes = []
        self.versions = []
        self.chat_scopes = []

    async def resolve_embedding(self, scope):
        self.scopes.append(scope)
        return EmbeddingRuntime(self.embedding, "fake-index", 2)

    async def resolve_embedding_version(self, version_id):
        self.versions.append(version_id)
        return EmbeddingRuntime(self.embedding, "fake-index", 2)

    async def resolve_chat(self, scope):
        self.chat_scopes.append(scope)
        return ChatRuntime(self.chat, "fake", "model")


class FakeVectorStore:
    def __init__(self) -> None:
        self.indexes = []
        self.deleted = []
        self.closed = 0
        self.error = None
        self.hits = []
        self.searches = []

    def ensure_index(self):
        pass

    def replace(self, index):
        self.indexes.append(index)
        if self.error:
            raise self.error

    def delete_document_version(self, version_id):
        self.deleted.append(version_id)

    def document_version_ids(self, workspace_id):
        return {i.document_version_id for i in self.indexes if i.scope.workspace_id == workspace_id}

    def close(self):
        self.closed += 1

    async def search(self, scope, query, query_vector, limit):
        self.searches.append((scope, query, query_vector, limit))
        return self.hits[:limit]


class FakeUploadRepository:
    def __init__(self):
        self.exists = True
        self.uploads = []
        self.receipt = UploadReceipt(uuid4(), uuid4(), uuid4(), "QUEUED", datetime.now(UTC))
        self.failures = []
        self.commits = 0
        self.rollbacks = 0
        self.error = None

    async def workspace_exists(self, organization_id, workspace_id):
        return self.exists

    async def create_upload(self, **kwargs):
        if self.error:
            raise self.error
        self.uploads.append(kwargs)
        return self.receipt

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def mark_queue_failure(self, version_id, message):
        self.failures.append((version_id, message))
