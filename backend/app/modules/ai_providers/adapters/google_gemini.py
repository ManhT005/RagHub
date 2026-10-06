from app.modules.ai_providers.adapters.openai_compatible import (
    OpenAICompatibleChatProvider,
    OpenAICompatibleEmbeddingProvider,
)


class GoogleGeminiEmbeddingProvider(OpenAICompatibleEmbeddingProvider):
    batch_stride = 24

    def __init__(self, **kwargs: object) -> None:
        super().__init__(provider_name="GOOGLE_GEMINI", **kwargs)

    async def _embed(self, texts, input_type="passage"):
        if self.model not in {"gemini-embedding-2", "gemini-embedding-001"}:
            return await super()._embed(texts, input_type)
        from app.modules.ai_providers.adapters.http import ProviderHttp, validate_vectors

        client = ProviderHttp(
            base_url=self.base_url.removesuffix("/openai"),
            secret=self.secret,
            provider_name=self.provider_name,
            policy=self.policy,
            native_google=True,
        )
        vectors = []
        # embedContent aggregates contents. Send each chunk separately to preserve cardinality.
        for text in texts:
            instruction = (
                "Represent this query for retrieving relevant documents: "
                if input_type == "query"
                else "Represent this document for retrieval: "
            )
            payload = {"content": {"parts": [{"text": instruction + text}]}}
            if self.model == "gemini-embedding-001":
                payload["content"]["parts"] = [{"text": text}]
                payload["taskType"] = (
                    "RETRIEVAL_QUERY" if input_type == "query" else "RETRIEVAL_DOCUMENT"
                )
            if self.metadata.dimension:
                payload["outputDimensionality"] = self.metadata.dimension
            data = await client.request(f"/models/{self.model}:embedContent", payload)
            vector = data.get("embedding", {}).get("values") if isinstance(data, dict) else None
            vectors.extend(validate_vectors([vector], 1, self.metadata.dimension or None))
        return vectors


class GoogleGeminiChatProvider(OpenAICompatibleChatProvider):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(provider_name="GOOGLE_GEMINI", **kwargs)
