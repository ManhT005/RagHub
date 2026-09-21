import uuid
from datetime import UTC, datetime
from typing import Any

from elasticsearch import AsyncElasticsearch, Elasticsearch, helpers

from app.core.config import Settings, get_settings
from app.modules.ingestion.chunker import TextChunk


def chunk_index_mapping() -> dict[str, Any]:
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
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = Elasticsearch(self.settings.elasticsearch_url)

    def close(self) -> None:
        self.client.close()

    def ensure_index(self) -> None:
        index = self.settings.elasticsearch_index
        alias = self.settings.elasticsearch_alias
        if not self.client.indices.exists(index=index):
            self.client.indices.create(index=index, **chunk_index_mapping())
        if not self.client.indices.exists_alias(name=alias):
            self.client.indices.put_alias(index=index, name=alias)

    def replace_document_version(
        self,
        *,
        organization_id: uuid.UUID,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        source_name: str,
        chunks: list[TextChunk],
    ) -> None:
        self.ensure_index()
        index = self.settings.elasticsearch_index
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
                    "source_name": source_name,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "language": "vi",
                    "created_at": now,
                },
            }
            for chunk in chunks
        ]
        if actions:
            helpers.bulk(self.client, actions, refresh="wait_for")


class ChunkSearch:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = AsyncElasticsearch(self.settings.elasticsearch_url)

    async def close(self) -> None:
        await self.client.close()

    async def search(
        self,
        *,
        organization_id: uuid.UUID,
        workspace_id: uuid.UUID,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        response = await self.client.search(
            index=self.settings.elasticsearch_alias,
            query={
                "bool": {
                    "must": [{"match": {"content": {"query": query}}}],
                    "filter": [
                        {"term": {"organization_id": str(organization_id)}},
                        {"term": {"workspace_id": str(workspace_id)}},
                    ],
                }
            },
            size=limit,
            source=[
                "document_id",
                "document_version_id",
                "chunk_id",
                "content",
                "source_name",
                "page_number",
            ],
        )
        return [
            {**hit["_source"], "score": hit.get("_score") or 0.0}
            for hit in response["hits"]["hits"]
        ]
