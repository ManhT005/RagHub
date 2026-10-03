from uuid import uuid4

from app.core_domain.ingestion.chunker import chunk_sections
from app.core_domain.ingestion.parser import parse_document
from app.core_domain.retrieval.models import DocumentIndex, IndexedChunk, RetrievalScope
from app.infrastructure.elasticsearch.vector_store import ElasticsearchVectorStore
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.task_queue.queue import CeleryTaskQueue
from app.ports.object_storage import ObjectStoragePort
from app.ports.task_queue import TaskQueuePort
from app.ports.vector_store import VectorStorePort


def test_existing_adapters_satisfy_ports_without_connections() -> None:
    assert isinstance(object.__new__(MinioObjectStorage), ObjectStoragePort)
    assert isinstance(CeleryTaskQueue(), TaskQueuePort)
    assert isinstance(object.__new__(ElasticsearchVectorStore), VectorStorePort)


def test_vector_adapter_preserves_scope_ids_and_vectors() -> None:
    class RecordingStore(ElasticsearchVectorStore):
        def __init__(self) -> None:
            self.calls = []

        def replace_document_version(self, **kwargs: object) -> None:
            self.calls.append(kwargs)

    scope = RetrievalScope(uuid4(), uuid4())
    version_id, document_id = uuid4(), uuid4()
    chunk = chunk_sections(parse_document(b"knowledge", "a.txt"), version_id)[0]
    store = RecordingStore()
    store.replace(DocumentIndex(scope, document_id, version_id, "a.txt", (
        IndexedChunk(chunk, (1.0, 0.0)),
    )))
    assert store.calls[0]["organization_id"] == scope.organization_id
    assert store.calls[0]["workspace_id"] == scope.workspace_id
    assert store.calls[0]["document_version_id"] == version_id
    assert store.calls[0]["embeddings"] == {str(chunk.chunk_id): [1.0, 0.0]}
