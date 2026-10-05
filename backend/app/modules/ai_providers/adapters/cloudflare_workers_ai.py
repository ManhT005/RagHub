import re

from raghub_core.domain.providers.contracts import EmbeddingMetadata, RerankResult
from raghub_core.domain.providers.errors import (
    ProviderConfigurationError,
    ProviderInvalidResponseError,
)

from app.modules.ai_providers.adapters.http import ProviderHttp, validate_vectors
from app.modules.ai_providers.adapters.openai_compatible import OpenAICompatibleChatProvider
from app.modules.ai_providers.adapters.rerank import normalized_rerank


def validate_model(model):
    if not re.fullmatch(r"@[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+", model) or ".." in model:
        raise ProviderConfigurationError("Use a valid Workers AI model ID.")


class CloudflareChatProvider(OpenAICompatibleChatProvider):
    def __init__(self, *, base_url, **kwargs):
        super().__init__(base_url=base_url + "/v1", provider_name="CLOUDFLARE_WORKERS_AI", **kwargs)


class CloudflareEmbeddingProvider(ProviderHttp):
    def __init__(self, *, model, dimension, **kwargs):
        super().__init__(provider_name="CLOUDFLARE_WORKERS_AI", **kwargs)
        validate_model(model)
        self.model, self.dimension = model, dimension
        self.metadata = EmbeddingMetadata(self.provider_name, model, dimension)

    async def _embed(self, texts):
        data = await self.request("/run/" + self.model, {"text": texts})
        if not isinstance(data, dict) or data.get("success") is False:
            raise ProviderInvalidResponseError()
        result = data.get("result", {})
        vectors = result.get("data") if isinstance(result, dict) else None
        return validate_vectors(vectors, len(texts), self.dimension or None)

    async def embed_documents(self, texts):
        vectors = []
        for start in range(0, len(texts), 32):
            vectors.extend(await self._embed(texts[start : start + 32]))
        return vectors

    async def embed_query(self, text):
        return (await self._embed([text]))[0]


class CloudflareRerankProvider(ProviderHttp):
    def __init__(self, *, model, **kwargs):
        super().__init__(provider_name="CLOUDFLARE_WORKERS_AI", **kwargs)
        validate_model(model)
        self.model = model

    async def rerank(self, *, query, documents, top_n):
        if not documents:
            return RerankResult([], self.model, self.provider_name)
        if not 1 <= top_n <= 1000 or len(documents) > 1000:
            raise ProviderConfigurationError("Rerank request exceeds supported limits.")
        data = await self.request(
            "/run/" + self.model,
            {
                "query": query,
                "contexts": [{"text": text} for text in documents],
                "top_k": min(top_n, len(documents)),
            },
        )
        if not isinstance(data, dict) or data.get("success") is False:
            raise ProviderInvalidResponseError()
        rows = data.get("result")
        if isinstance(rows, dict):
            rows = rows.get("response")
        return normalized_rerank(
            rows,
            model=self.model,
            provider=self.provider_name,
            count=len(documents),
            top_n=top_n,
            index_key="id",
            score_key="score",
        )
