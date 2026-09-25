import hashlib
import math
import re

from app.modules.ai_providers.contracts import EmbeddingMetadata


class LocalTokenHashEmbeddingProvider:
    """Lightweight deterministic embeddings for development and integration tests."""

    provider_name = "LOCAL_TOKEN_HASH"

    def __init__(self, *, model: str, dimension: int) -> None:
        self.model = model
        self.metadata = EmbeddingMetadata(self.provider_name, model, dimension)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.metadata.dimension
        for token in re.findall(r"\w+", text.casefold()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:8], "big") % self.metadata.dimension
            vector[index] += 1.0 if digest[8] & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
