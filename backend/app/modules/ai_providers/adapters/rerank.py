from raghub_core.domain.providers.contracts import RerankItem, RerankResult
from raghub_core.domain.providers.errors import ProviderInvalidResponseError
from raghub_core.domain.providers.rerank import validated_rerank_indices

from app.modules.ai_providers.adapters.http import ProviderHttp


def normalized_rerank(
    rows, *, model, provider, count, top_n, index_key="index", score_key="relevance_score"
):
    try:
        result = RerankResult(
            [RerankItem(row[index_key], row[score_key]) for row in rows], model, provider
        )
        indices = validated_rerank_indices(result, count, top_n)
        by_index = {item.index: item for item in result.items}
        return RerankResult([by_index[index] for index in indices], model, provider)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ProviderInvalidResponseError() from exc


class JsonRerankProvider(ProviderHttp):
    def __init__(self, *, model, top_field="top_n", result_field="results", **kwargs):
        super().__init__(**kwargs)
        self.model, self.top_field, self.result_field = model, top_field, result_field

    async def rerank(self, *, query, documents, top_n):
        if not documents:
            return RerankResult([], self.model, self.provider_name)
        if not 1 <= top_n <= 1000 or len(documents) > 1000:
            raise ValueError("Rerank request exceeds safe bounds")
        data = await self.request(
            "/rerank",
            {
                "model": self.model,
                "query": query,
                "documents": documents,
                self.top_field: min(top_n, len(documents)),
                "return_documents": False,
            },
        )
        if not isinstance(data, dict) or not isinstance(data.get(self.result_field), list):
            raise ProviderInvalidResponseError()
        return normalized_rerank(
            data[self.result_field],
            model=self.model,
            provider=self.provider_name,
            count=len(documents),
            top_n=top_n,
        )
