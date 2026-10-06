import time
import uuid
from datetime import UTC, datetime
from typing import Any

from elasticsearch import AsyncElasticsearch, Elasticsearch, helpers
from raghub_core.domain.ingestion.chunker import TextChunk
from raghub_core.domain.retrieval.hybrid import (
    MAPPING_VERSION,
    RETRIEVAL_CANDIDATES,
    fuse_rrf,
    resolve_candidate_count,
)
from raghub_core.ports.telemetry import TelemetryPort

from app.core.config import Settings, get_settings
from app.infrastructure.retrieval_mapping import chunk_from_hit, chunk_to_hit

BOOST_EXACT = 1.0
BOOST_FOLDED = 0.8
BOOST_HEADING = 2.0
BOOST_SOURCE_NAME = 1.2


def chunk_index_mapping(
    dimension: int, *, mapping_version: str = MAPPING_VERSION
) -> dict[str, Any]:
    if dimension < 1:
        raise ValueError("Embedding dimension must be positive")
    return {
        "settings": {
            "analysis": {
                "analyzer": {
                    "vi_folded": {
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding"],
                    }
                }
            }
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "organization_id": {"type": "keyword"},
                "workspace_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                "document_version_id": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "content": {
                    "type": "text",
                    "fields": {"folded": {"type": "text", "analyzer": "vi_folded"}},
                },
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
                "retrievable": {"type": "boolean"},
                "mapping_version": {"type": "keyword"},
                "created_at": {"type": "date"},
            },
        },
    }


def bm25_query(query: str, organization_id: uuid.UUID, workspace_id: uuid.UUID) -> dict[str, Any]:
    """Multi-match Vietnamese query with tenant/retrievable filters pre-cutoff."""
    return {
        "bool": {
            "must": [
                {
                    "multi_match": {
                        "query": query,
                        "fields": [
                            f"content^{BOOST_EXACT}",
                            f"content.folded^{BOOST_FOLDED}",
                            f"heading.text^{BOOST_HEADING}",
                            f"source_name.text^{BOOST_SOURCE_NAME}",
                        ],
                    }
                }
            ],
            "filter": [
                {"term": {"organization_id": str(organization_id)}},
                {"term": {"workspace_id": str(workspace_id)}},
                {"term": {"retrievable": True}},
            ],
        }
    }


def knn_query(
    query_vector: list[float],
    organization_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    k: int,
    num_candidates: int,
) -> dict[str, Any]:
    return {
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": k,
            "num_candidates": num_candidates,
            "filter": [
                {"term": {"organization_id": str(organization_id)}},
                {"term": {"workspace_id": str(workspace_id)}},
                {"term": {"retrievable": True}},
            ],
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
                    "retrievable": False,
                    "mapping_version": MAPPING_VERSION,
                    "created_at": now,
                },
            }
            for chunk in chunks
        ]
        if actions:
            helpers.bulk(self.client, actions, refresh="wait_for")
        result = self.client.count(
            index=index,
            query={"term": {"document_version_id": str(document_version_id)}},
        )
        if result["count"] != len(chunks):
            raise ValueError("Indexed chunk count does not match the document manifest.")
        self.set_version_retrievable(document_version_id, retrievable=True)

    def set_version_retrievable(
        self, document_version_id: uuid.UUID, *, retrievable: bool
    ) -> None:
        """Flip the pre-cutoff retrievable flag without reindexing content."""
        self.ensure_index()
        result = self.client.update_by_query(
            index=self.index_name,
            query={"term": {"document_version_id": str(document_version_id)}},
            script={
                "source": "ctx._source.retrievable = params.flag",
                "params": {"flag": retrievable},
            },
            conflicts="abort",
            refresh=True,
        )
        body = getattr(result, "body", result)
        if isinstance(body, dict) and (
            body.get("failures") or body.get("timed_out") or body.get("version_conflicts")
        ):
            raise ValueError("Document publication did not complete successfully.")

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
    def __init__(
        self,
        *,
        index_name: str,
        settings: Settings | None = None,
        telemetry: TelemetryPort | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.index_name = index_name
        self.telemetry = telemetry
        self.client = AsyncElasticsearch(self.settings.elasticsearch_url)

    async def close(self) -> None:
        await self.client.close()

    def _candidates(self) -> int:
        try:
            return resolve_candidate_count(self.settings.rag_retrieval_candidates)
        except (ValueError, AttributeError):
            return RETRIEVAL_CANDIDATES

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

        started = time.perf_counter()
        lexical, vector = await asyncio.gather(
            self._search_bm25(organization_id, workspace_id, query),
            self._search_vector(organization_id, workspace_id, query_vector),
        )
        mark = time.perf_counter()
        fused = fuse_rrf(
            [[chunk_from_hit(hit) for hit in ranking] for ranking in (lexical, vector)],
            limit=limit,
            max_per_document=self._doc_cap(),
            rrf_k=self.settings.rag_rrf_k,
        )
        if self.telemetry is not None:
            labels = {"stage": "retrieval"}
            self.telemetry.timing(
                "retrieval_rrf_diversity", (time.perf_counter() - mark) * 1000, labels
            )
            self.telemetry.timing(
                "retrieval_es_total", (time.perf_counter() - started) * 1000, labels
            )
            self.telemetry.counter("retrieval_bm25_hits", labels, len(lexical))
            self.telemetry.counter("retrieval_vector_hits", labels, len(vector))
            self.telemetry.counter("retrieval_fused_hits", labels, len(fused))
        return [chunk_to_hit(hit) for hit in fused]

    def _doc_cap(self) -> int | None:
        try:
            return int(self.settings.rag_max_chunks_per_document)
        except (ValueError, TypeError, AttributeError):
            return None

    async def search_branches(
        self,
        *,
        organization_id: uuid.UUID,
        workspace_id: uuid.UUID,
        query: str,
        query_vector: list[float],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Raw per-branch hits (lexical, vector) for explainability/telemetry."""
        import asyncio

        return await asyncio.gather(
            self._search_bm25(organization_id, workspace_id, query),
            self._search_vector(organization_id, workspace_id, query_vector),
        )

    async def _search_bm25(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID, query: str
    ) -> list[dict[str, Any]]:
        mark = time.perf_counter()
        response = await self.client.search(
            index=self.index_name,
            query=bm25_query(query, organization_id, workspace_id),
            size=self._candidates(),
            source=self._source_fields(),
        )
        hits = self._hits(response)
        if self.telemetry is not None:
            self.telemetry.timing(
                "retrieval_es_bm25", (time.perf_counter() - mark) * 1000, {"stage": "retrieval"}
            )
        return hits

    async def _search_vector(
        self, organization_id: uuid.UUID, workspace_id: uuid.UUID, query_vector: list[float]
    ) -> list[dict[str, Any]]:
        candidates = self._candidates()
        mark = time.perf_counter()
        response = await self.client.search(
            index=self.index_name,
            query=knn_query(
                query_vector,
                organization_id,
                workspace_id,
                k=candidates,
                num_candidates=candidates * 4,
            ),
            size=candidates,
            source=self._source_fields(),
        )
        hits = self._hits(response)
        if self.telemetry is not None:
            self.telemetry.timing(
                "retrieval_es_vector", (time.perf_counter() - mark) * 1000, {"stage": "retrieval"}
            )
        return hits

    @staticmethod
    def _source_fields() -> list[str]:
        return [
            "chunk_index",
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
