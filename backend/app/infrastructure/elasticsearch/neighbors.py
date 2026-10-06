from elasticsearch import AsyncElasticsearch

from app.infrastructure.retrieval_mapping import chunk_from_hit


class NeighborExpansion:
    def __init__(self, settings):
        self.settings = settings

    async def expand(self, runtime, scope, seeds):
        from dataclasses import replace

        windows = [
            {
                "bool": {
                    "filter": [
                        {"term": {"document_version_id": str(seed.document_version_id)}},
                        {
                            "range": {
                                "chunk_index": {
                                    "gte": max(0, seed.chunk_index - 1),
                                    "lte": seed.chunk_index + 1,
                                }
                            }
                        },
                    ]
                }
            }
            for seed in seeds
            if seed.chunk_index is not None
        ]
        if not windows:
            return seeds
        client = AsyncElasticsearch(self.settings.elasticsearch_url)
        try:
            result = await client.search(
                index=runtime.index_name,
                size=len(windows) * 3,
                query={
                    "bool": {
                        "filter": [
                            {"term": {"organization_id": str(scope.organization_id)}},
                            {"term": {"workspace_id": str(scope.workspace_id)}},
                            {"term": {"retrievable": True}},
                        ],
                        "should": windows,
                        "minimum_should_match": 1,
                    }
                },
                source_excludes=["embedding"],
                sort=[{"chunk_index": "asc"}],
            )
            expanded, seen = list(seeds), {s.chunk_id for s in seeds}
            for hit in result["hits"]["hits"]:
                chunk = chunk_from_hit({**hit["_source"], "score": 0.0})
                if chunk.chunk_id in seen:
                    continue
                parents = [s for s in seeds if s.document_version_id == chunk.document_version_id]
                if parents:
                    expanded.append(replace(chunk, score=max(s.score for s in parents)))
                    seen.add(chunk.chunk_id)
            return expanded
        finally:
            await client.close()
