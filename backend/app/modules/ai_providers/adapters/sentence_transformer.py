import asyncio
import math
from collections.abc import Callable
from threading import Lock
from typing import Any

from app.modules.ai_providers.contracts import EmbeddingMetadata
from app.modules.ai_providers.errors import (
    ProviderConfigurationError,
    ProviderInvalidResponseError,
)


class SentenceTransformerModelRegistry:
    _models: dict[str, Any] = {}
    _lock = Lock()

    @classmethod
    def get(cls, model_name: str) -> Any:
        with cls._lock:
            if model_name not in cls._models:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise ProviderConfigurationError(
                        "Install the local-ai optional dependency to use local embeddings."
                    ) from exc
                cls._models[model_name] = SentenceTransformer(model_name)
            return cls._models[model_name]


class LocalSentenceTransformerProvider:
    provider_name = "LOCAL_SENTENCE_TRANSFORMER"
    _semaphores: dict[int, asyncio.Semaphore] = {}

    def __init__(
        self,
        *,
        model: str,
        dimension: int,
        batch_size: int = 32,
        max_concurrency: int = 2,
        model_loader: Callable[[str], Any] | None = None,
    ) -> None:
        self.model = model
        self.metadata = EmbeddingMetadata(self.provider_name, model, dimension)
        self.batch_size = max(1, min(batch_size, 256))
        self._model_loader = model_loader or SentenceTransformerModelRegistry.get
        self._max_concurrency = max(1, max_concurrency)

    def _semaphore(self) -> asyncio.Semaphore:
        loop_id = id(asyncio.get_running_loop())
        return self._semaphores.setdefault(loop_id, asyncio.Semaphore(self._max_concurrency))

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._model_loader(self.model)
        encoded = model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)
        result = [[float(value) for value in vector] for vector in vectors]
        for vector in result:
            if len(vector) != self.metadata.dimension or not all(map(math.isfinite, vector)):
                raise ProviderInvalidResponseError(
                    "Local embedding dimension does not match config."
                )
        return result

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with self._semaphore():
            return await asyncio.to_thread(self._encode, texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]
