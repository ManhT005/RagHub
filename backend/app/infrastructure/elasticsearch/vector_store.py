from elasticsearch import NotFoundError

from app.core_domain.errors import AppError
from app.core_domain.providers.errors import ProviderError
from app.core_domain.retrieval.models import DocumentIndex, RetrievalScope, RetrievedChunk
from app.infrastructure.elasticsearch.chunks import ChunkIndexer, ChunkSearch


class ElasticsearchVectorStore(ChunkIndexer):
    def replace(self, index: DocumentIndex) -> None:
        self.replace_document_version(
            organization_id=index.scope.organization_id,
            workspace_id=index.scope.workspace_id, document_id=index.document_id,
            document_version_id=index.document_version_id, source_name=index.source_name,
            chunks=[item.chunk for item in index.chunks],
            embeddings={str(item.chunk.chunk_id): list(item.embedding) for item in index.chunks},
        )


class ElasticsearchVectorSearch:
    def __init__(self, search: ChunkSearch) -> None:
        self.search_adapter = search

    async def search(
        self, scope: RetrievalScope, query: str, query_vector: list[float], limit: int
    ) -> list[RetrievedChunk]:
        try:
            hits = await self.search_adapter.search(
                organization_id=scope.organization_id, workspace_id=scope.workspace_id,
                query=query, query_vector=query_vector, limit=limit,
            )
            return [RetrievedChunk.from_hit(hit) for hit in hits]
        except NotFoundError:
            return []
        except ProviderError:
            raise
        except Exception as exc:
            raise AppError(
                "SEARCH_UNAVAILABLE", "Search is temporarily unavailable.", status_code=503
            ) from exc

    async def close(self) -> None:
        await self.search_adapter.close()
