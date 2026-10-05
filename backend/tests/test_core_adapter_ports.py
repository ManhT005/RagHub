from uuid import uuid4

from raghub_core.domain.ingestion.chunker import chunk_sections
from raghub_core.domain.ingestion.parser import ParsedSection, parse_document
from raghub_core.domain.providers.errors import ProviderTimeoutError
from raghub_core.domain.retrieval.models import DocumentIndex, IndexedChunk, RetrievalScope
from raghub_core.ports.object_storage import ObjectStoragePort
from raghub_core.ports.task_queue import TaskQueuePort
from raghub_core.ports.vector_store import VectorStorePort

from app.infrastructure.elasticsearch.vector_store import ElasticsearchVectorStore
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.task_queue.queue import CeleryTaskQueue


def test_compatibility_exports_preserve_identity() -> None:
    from app.modules.ai_providers.errors import ProviderTimeoutError as LegacyError
    from app.modules.ingestion.chunker import chunk_sections as legacy_chunker
    from app.modules.ingestion.parser import ParsedSection as LegacySection

    assert LegacyError is ProviderTimeoutError
    assert legacy_chunker is chunk_sections
    assert LegacySection is ParsedSection


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
