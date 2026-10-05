from raghub_core.domain.providers.contracts import EmbeddingMetadata
from raghub_core.domain.providers.errors import ProviderInvalidResponseError

from app.modules.ai_providers.adapters.http import ProviderHttp, validate_vectors
from app.modules.ai_providers.adapters.rerank import JsonRerankProvider


def indexed_rows(rows, count):
    if not isinstance(rows, list) or len(rows) != count:
        raise ProviderInvalidResponseError()
    try:
        indices = [row["index"] for row in rows]
        if any(type(index) is not int for index in indices) or set(indices) != set(range(count)):
            raise ProviderInvalidResponseError()
        return sorted(rows, key=lambda row: row["index"])
    except (KeyError, TypeError) as exc:
        raise ProviderInvalidResponseError() from exc


class VoyageEmbeddingProvider(ProviderHttp):
    def __init__(self, *, model, dimension, batch_limit=128, **kwargs):
        super().__init__(provider_name="VOYAGE", **kwargs)
        self.model, self.dimension = model, dimension
        self.metadata = EmbeddingMetadata(self.provider_name, model, dimension)
        self.batch_limit = min(128, max(1, batch_limit))
        self.last_usage = None

    async def _embed(self, texts, input_type):
        contextual = self.model.startswith("voyage-context-")
        payload = {"model": self.model, "input_type": input_type}
        payload["inputs" if contextual else "input"] = (
            [[text] for text in texts] if contextual else texts
        )
        if self.dimension and (
            self.model.startswith(("voyage-4", "voyage-context-", "voyage-3-large", "voyage-3.5"))
        ):
            payload["output_dimension"] = self.dimension
        data = await self.request(
            "/contextualizedembeddings" if contextual else "/embeddings", payload
        )
        try:
            rows = indexed_rows(data["data"], len(texts))
            if contextual:
                vectors = [indexed_rows(row["data"], 1)[0]["embedding"] for row in rows]
            else:
                vectors = [row["embedding"] for row in rows]
            self.last_usage = {
                "input_count": len(texts),
                "provider_reported_tokens": data.get("usage", {}).get("total_tokens"),
                "usage_source": "provider" if data.get("usage") else "unavailable",
            }
            return validate_vectors(vectors, len(texts), self.dimension or None)
        except (KeyError, TypeError, AttributeError) as exc:
            raise ProviderInvalidResponseError() from exc

    async def embed_documents(self, texts):
        vectors = []
        for start in range(0, len(texts), self.batch_limit):
            vectors.extend(await self._embed(texts[start : start + self.batch_limit], "document"))
        return vectors

    async def embed_query(self, text):
        return (await self._embed([text], "query"))[0]


class VoyageRerankProvider(JsonRerankProvider):
    def __init__(self, **kwargs):
        super().__init__(provider_name="VOYAGE", top_field="top_k", result_field="data", **kwargs)
