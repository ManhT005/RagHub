from elasticsearch import NotFoundError

from app.core_domain.errors import CoreError
from app.core_domain.ingestion.errors import IngestionError
from app.core_domain.providers.errors import ProviderError
from app.core_domain.retrieval.models import DocumentIndex, RetrievalScope, RetrievedChunk
from app.infrastructure.elasticsearch.chunks import ChunkIndexer, ChunkSearch


class ElasticsearchVectorStore(ChunkIndexer):
    def replace(self, index: DocumentIndex) -> None:
        self.replace_document_version(
            organization_id=index.scope.organization_id,
            workspace_id=index.scope.workspace_id,
            document_id=index.document_id,
            document_version_id=index.document_version_id,
            source_name=index.source_name,
            chunks=[item.chunk for item in index.chunks],
            embeddings={str(item.chunk.chunk_id): list(item.embedding) for item in index.chunks},
        )


class LegacyVectorStoreAdapter:
    """Adapt the existing indexer without changing its compatibility interface."""

    def __init__(self, indexer: ChunkIndexer) -> None:
        self.indexer = indexer

    def ensure_index(self) -> None:
        try:
            self.indexer.ensure_index()
        except Exception as exc:
            raise IngestionError("INDEX_UNAVAILABLE", str(exc), retryable=True) from exc

    def replace(self, index: DocumentIndex) -> None:
        try:
            ElasticsearchVectorStore.replace(self.indexer, index)
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
            transient = status in {429, 502, 503, 504} or isinstance(
                exc, ConnectionError | TimeoutError
            )
            transient = transient or exc.__class__.__module__.split(".")[0] in {
                "elastic_transport",
                "urllib3",
            }
            raise IngestionError(
                "INDEX_UNAVAILABLE" if transient else "INDEX_FAILED", str(exc), retryable=transient
            ) from exc

    def delete_document_version(self, document_version_id) -> None:
        self.indexer.delete_document_version(document_version_id)

    def document_version_ids(self, workspace_id):
        try:
            return self.indexer.document_version_ids(workspace_id)
        except Exception as exc:
            raise IngestionError("INDEX_UNAVAILABLE", str(exc), retryable=True) from exc

    def close(self) -> None:
        self.indexer.close()


class ElasticsearchVectorSearch:
    def __init__(self, search: ChunkSearch) -> None:
        self.search_adapter = search

    async def search(
        self, scope: RetrievalScope, query: str, query_vector: list[float], limit: int
    ) -> list[RetrievedChunk]:
        try:
            hits = await self.search_adapter.search(
                organization_id=scope.organization_id,
                workspace_id=scope.workspace_id,
                query=query,
                query_vector=query_vector,
                limit=limit,
            )
            return [RetrievedChunk.from_hit(hit) for hit in hits]
        except NotFoundError:
            return []
        except ProviderError:
            raise
        except Exception as exc:
            raise CoreError("SEARCH_UNAVAILABLE", "Search is temporarily unavailable.") from exc

    async def close(self) -> None:
        await self.search_adapter.close()
