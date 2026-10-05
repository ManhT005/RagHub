import re

from raghub_core.domain.providers.contracts import EmbeddingMetadata
from raghub_core.domain.providers.errors import ProviderConfigurationError

from app.modules.ai_providers.adapters.http import ProviderHttp, validate_vectors
from app.modules.ai_providers.adapters.openai_compatible import OpenAICompatibleChatProvider


class HuggingFaceChatProvider(OpenAICompatibleChatProvider):
    def __init__(self, *, base_url, **kwargs):
        super().__init__(
            base_url=base_url.rstrip("/") + "/v1", provider_name="HUGGINGFACE_INFERENCE", **kwargs
        )


class HuggingFaceEmbeddingProvider(ProviderHttp):
    def __init__(self, *, model, dimension, **kwargs):
        super().__init__(provider_name="HUGGINGFACE_INFERENCE", **kwargs)
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", model) or ".." in model:
            raise ProviderConfigurationError("Use a valid Hugging Face repository ID.")
        self.model, self.dimension = model, dimension
        self.metadata = EmbeddingMetadata(self.provider_name, model, dimension)

    async def _embed(self, texts, input_type):
        # Require pooled sentence vectors; reject token matrices.
        payload = {"inputs": texts, "normalize": True}
        if self.model.startswith("intfloat/multilingual-e5"):
            payload["inputs"] = [
                ("query: " if input_type == "query" else "passage: ") + text for text in texts
            ]
        data = await self.request("/hf-inference/models/" + self.model, payload)
        if isinstance(data, list) and data and isinstance(data[0], int | float) and len(texts) == 1:
            data = [data]
        return validate_vectors(data, len(texts), self.dimension or None)

    async def embed_documents(self, texts):
        vectors = []
        for start in range(0, len(texts), 32):
            vectors.extend(await self._embed(texts[start : start + 32], "document"))
        return vectors

    async def embed_query(self, text):
        return (await self._embed([text], "query"))[0]
