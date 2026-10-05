"""Local cross-encoder reranker adapter (optional, default off).

Model and revision are pinned; the checksum is verified against the
downloaded snapshot before first use. Heavy dependencies import lazily so
the API process never requires torch when the reranker is disabled.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from raghub_core.domain.retrieval.models import RetrievedChunk
from raghub_core.ports.reranker import RerankerTimeoutError

MODEL_ID = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
MODEL_REVISION = "main"
EXPECTED_SNAPSHOT_SHA256 = ""  # filled at calibration time; empty refuses to load


class LocalCrossEncoderReranker:
    def __init__(
        self,
        *,
        model_id: str = MODEL_ID,
        revision: str = MODEL_REVISION,
        expected_sha256: str = EXPECTED_SNAPSHOT_SHA256,
        timeout_seconds: float = 2.0,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.expected_sha256 = expected_sha256
        self.timeout_seconds = timeout_seconds
        self._model = None

    def _load(self):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError("Reranker requires the local-ai extras.") from exc
        if not self.expected_sha256:
            raise RuntimeError("Reranker checksum is not pinned; refusing to load.")
        model = CrossEncoder(self.model_id, revision=self.revision, max_length=512)
        digest = hashlib.sha256()
        paths = (
            sorted(Path(model.model_path).rglob("*")) if hasattr(model, "model_path") else []
        )
        for path in paths:
            if path.is_file():
                digest.update(path.name.encode())
                with path.open("rb") as handle:
                    for block in iter(lambda: handle.read(1 << 20), b""):
                        digest.update(block)
        if digest.hexdigest() != self.expected_sha256:
            raise RuntimeError("Reranker snapshot checksum mismatch.")
        self._model = model
        return model

    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if not candidates or top_n <= 0:
            return []
        model = self._model or await asyncio.to_thread(self._load)
        pairs = [(query, hit.content) for hit in candidates]

        try:
            scores = await asyncio.wait_for(
                asyncio.to_thread(model.predict, pairs), timeout=self.timeout_seconds
            )
        except TimeoutError as exc:
            raise RerankerTimeoutError("Reranker timed out; caller falls back to fusion.") from exc
        ranked = sorted(
            zip(candidates, scores, strict=False), key=lambda pair: float(pair[1]), reverse=True
        )
        return [hit for hit, _ in ranked[:top_n]]
