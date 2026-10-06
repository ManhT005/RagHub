"""Tenant-scoped semantic embedding cache; corrupt entries are cache misses."""

import hashlib
import math

from raghub_core.domain.ingestion.tokenizer import ENCODING

from app.modules.ai_providers.work_items import decode_artifact, encode_artifact


class EmbeddingCache:
    def __init__(self, storage, organization_id, fingerprint, dimension, telemetry=None):
        self.storage = storage
        self.prefix = f"{organization_id}/embedding-cache/{fingerprint}"
        self.dimension = dimension
        self.telemetry = telemetry

    def key(self, text):
        return f"{self.prefix}/{hashlib.sha256(text.encode()).hexdigest()}.json.gz"

    def valid(self, vector):
        return len(vector) == self.dimension and all(math.isfinite(x) for x in vector)

    async def embed(self, texts, embed):
        vectors, missing = {}, {}
        for text in dict.fromkeys(texts):
            try:
                stored = decode_artifact(await self.storage.get(self.key(text)))
                if len(stored) != 1 or not self.valid(stored[0]):
                    raise ValueError("Invalid cached embedding")
                vectors[text] = stored[0]
            except Exception:
                missing[text] = None
        if self.telemetry is not None:
            self.telemetry.counter("embedding_cache_hits", {}, len(vectors))
            self.telemetry.counter("embedding_cache_misses", {}, len(missing))
            saved = [text for text in texts if text in vectors]
            duplicates = len(texts) - len(set(texts))
            self.telemetry.counter("embedding_cache_duplicate_chunks", {}, duplicates)
            self.telemetry.counter(
                "embedding_tokens_saved", {}, sum(len(ENCODING.encode(text)) for text in saved)
            )
            self.telemetry.counter(
                "embedding_provider_calls_saved", {}, int(bool(texts) and not missing)
            )
        if missing:
            fresh = await embed(list(missing))
            if len(fresh) != len(missing) or not all(self.valid(v) for v in fresh):
                raise ValueError("Invalid embedding response")
            for text, vector in zip(missing, fresh, strict=True):
                vectors[text] = vector
                await self.storage.put(
                    self.key(text), encode_artifact([vector]), "application/gzip"
                )
        return [vectors[text] for text in texts]
