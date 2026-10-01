import uuid
from datetime import UTC, datetime
from typing import Any

from elasticsearch import AsyncElasticsearch, Elasticsearch, helpers

from app.core.config import Settings, get_settings
from app.modules.ingestion.chunker import TextChunk
from app.modules.search.hybrid import RETRIEVAL_CANDIDATES, fuse_rrf


def chunk_index_mapping(dimension: int) -> dict[str, Any]:
    if dimension < 1:
        raise ValueError("Embedding dimension must be positive")
    return {
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "organization_id": {"type": "keyword"},
                "workspace_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                "document_version_id": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "content": {"type": "text"},
                "content_hash": {"type": "keyword"},
                "token_count": {"type": "integer"},
                "heading": {"type": "keyword", "fields": {"text": {"type": "text"}}},
                "embedding": {
                    "type": "dense_vector",
                    "dims": dimension,
                    "index": True,
                    "similarity": "cosine",
                },
                "source_name": {
                    "type": "keyword",
                    "fields": {"text": {"type": "text"}},
                },
                "page_number": {"type": "integer"},
                "chunk_index": {"type": "integer"},
                "language": {"type": "keyword"},
                "created_at": {"type": "date"},
            },
        }
    }


class ChunkIndexer:
    def __init__(
        self, *, index_name: str, dimension: int, settings: Settings | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.index_name = index_name
        self.dimension = dimension
        self.client = Elasticsearch(self.settings.elasticsearch_url)

    def close(self) -> None:
        self.client.close()

    def ensure_index(self) -> None:
        index = self.index_name
        if not self.client.indices.exists(index=index):
            self.client.indices.create(index=index, **chunk_index_mapping(self.dimension))
        else:
            properties = chunk_index_mapping(self.dimension)["mappings"]["properties"]
            self.client.indices.put_mapping(index=index, properties=properties)

    def delete_document_version(self, document_version_id: uuid.UUID) -> None:
        """Remove every indexed chunk before a version leaves READY."""
        self.ensure_index()
        self.client.delete_by_query(
            index=self.index_name,
            query={"term": {"document_version_id": str(document_version_id)}},
            conflicts="proceed",
            refresh=True,
        )

    def replace_document_version(
        self,
        *,
        organization_id: uuid.UUID,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        source_name: str,
        chunks: list[TextChunk],
        embeddings: dict[str, list[float]],
    ) -> None:
        self.ensure_index()
        index = self.index_name
        self.client.delete_by_query(
            index=index,
            query={"term": {"document_version_id": str(document_version_id)}},
            conflicts="proceed",
            refresh=True,
        )
        now = datetime.now(UTC).isoformat()
        actions = [
            {
                "_op_type": "index",
                "_index": index,
                "_id": str(chunk.chunk_id),
                "_source": {
                    "organization_id": str(organization_id),
                    "workspace_id": str(workspace_id),
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "chunk_id": str(chunk.chunk_id),
                    "content": chunk.content,
                    "source_name": chunk.source_name,
                    "page_number": chunk.page_number,
                    "heading": chunk.heading,
                    "content_hash": chunk.content_hash,
                    "token_count": chunk.token_count,
                    "embedding": embeddings[str(chunk.chunk_id)],
                    "chunk_index": chunk.chunk_index,
                    "language": "vi",
                    "created_at": now,
                },
            }
            for chunk in chunks
        ]
        if actions:
            helpers.bulk(self.client, actions, refresh="wait_for")

    def document_version_ids(self, workspace_id: uuid.UUID) -> set[uuid.UUID]:
        """Return distinct indexed document versions for a workspace."""
        values: set[uuid.UUID] = set()
        after: dict[str, Any] | None = None
        while True:
            composite: dict[str, Any] = {
                "size": 1000,
                "sources": [{"version_id": {"terms": {"field": "document_version_id"}}}],
            }
            if after:
                composite["after"] = after
            response = self.client.search(
                index=self.index_name,
                size=0,
                query={"term": {"workspace_id": str(workspace_id)}},
                aggregations={"versions": {"composite": composite}},
            )
            aggregation = response["aggregations"]["versions"]
            values.update(
                uuid.UUID(bucket["key"]["version_id"]) for bucket in aggregation["buckets"]
            )
            after = aggregation.get("after_key")
            if not after:
                return values


class ChunkSearch:
    def __init__(self, *, index_name: str, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.index_name = index_name
        self.client = AsyncElasticsearch(self.settings.elasticsearch_url)

    async def close(self) -> None:
        await self.client.close()

    async def search(
        self,
        *,
        organization_id: uuid.UUID,
        workspace_id: uuid.UUID,
        query: str,
        query_vector: list[float],
        limit: int,
    ) -> list[dict[str, Any]]:
        import asyncio

        lexical, vector = await asyncio.gather(
            self._search_bm25(organization_id, workspace_id, query),
            self._search_vector(organization_id, workspace_id, query_vector),
        )
        return fuse_rrf([lexical, vector], limit=limit)

    async def _search_bm25(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID, query: str
    ) -> list[dict[str, Any]]:
        response = await self.client.search(
            index=self.index_name,
            query={
                "bool": {
                    "must": [{"match": {"content": {"query": query}}}],
                    "filter": [
                        {"term": {"organization_id": str(organization_id)}},
                        {"term": {"workspace_id": str(workspace_id)}},
                    ],
                }
            },
            size=RETRIEVAL_CANDIDATES,
            source=self._source_fields(),
        )
        return self._hits(response)

    async def _search_vector(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID, query_vector: list[float]
    ) -> list[dict[str, Any]]:
        response = await self.client.search(
            index=self.index_name,
            query={
                "knn": {
                    "field": "embedding",
                    "query_vector": query_vector,
                    "k": RETRIEVAL_CANDIDATES,
                    "num_candidates": RETRIEVAL_CANDIDATES * 4,
                    "filter": [
                        {"term": {"organization_id": str(organization_id)}},
                        {"term": {"workspace_id": str(workspace_id)}},
                    ],
                }
            },
            size=RETRIEVAL_CANDIDATES,
            source=self._source_fields(),
        )
        return self._hits(response)

    @staticmethod
    def _source_fields() -> list[str]:
        return [
            "document_id",
            "document_version_id",
            "chunk_id",
            "content",
            "source_name",
            "page_number",
            "heading",
        ]

    @staticmethod
    def _hits(response: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {**hit["_source"], "score": hit.get("_score") or 0.0}
            for hit in response["hits"]["hits"]
        ]
