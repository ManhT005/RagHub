"""Local cross-encoder reranker adapter (optional, default off).

Model and revision are pinned; the checksum is verified against the
downloaded snapshot before first use. Heavy dependencies import lazily so
the API process never requires torch when the reranker is disabled.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
import threading
from pathlib import Path

from raghub_core.domain.retrieval.models import RetrievedChunk
from raghub_core.ports.reranker import RerankerTimeoutError

MODEL_ID = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
MODEL_REVISION = "1427fd652930e4ba29e8149678df786c240d8825"
EXPECTED_SNAPSHOT_SHA256 = ""  # filled at calibration time; empty refuses to load


def snapshot_sha256(directory: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(p for p in directory.rglob("*") if p.is_file() and ".cache" not in p.parts)
    if not files:
        raise RuntimeError("Reranker snapshot is empty.")
    for path in files:
        digest.update(path.relative_to(directory).as_posix().encode())
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    return digest.hexdigest()


class LocalCrossEncoderReranker:
    def __init__(
        self,
        *,
        model_id: str = MODEL_ID,
        revision: str = MODEL_REVISION,
        expected_sha256: str = EXPECTED_SNAPSHOT_SHA256,
        timeout_seconds: float = 2.0,
        snapshot_path: str = "",
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.expected_sha256 = expected_sha256
        self.timeout_seconds = timeout_seconds
        self._model = None
        self.snapshot_path = snapshot_path
        self._slot = threading.Lock()

    def _load(self):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError("Reranker requires the local-ai extras.") from exc
        if not re.fullmatch(r"[0-9a-f]{40}", self.revision):
            raise RuntimeError("Reranker revision must be a commit SHA.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.expected_sha256):
            raise RuntimeError("Reranker checksum is not pinned; refusing to load.")
        if self.snapshot_path:
            snapshot = Path(self.snapshot_path)
        else:
            from huggingface_hub import snapshot_download

            snapshot = Path(
                snapshot_download(self.model_id, revision=self.revision, local_files_only=True)
            )
        # Verify before loading weights; runtime never downloads an unreviewed model.
        if snapshot_sha256(snapshot) != self.expected_sha256:
            raise RuntimeError("Reranker snapshot checksum mismatch.")
        model = CrossEncoder(str(snapshot), max_length=512, trust_remote_code=False)
        self._model = model
        return model

    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if not candidates or top_n <= 0:
            return []
        pairs = [(query, hit.content) for hit in candidates]

        def predict():
            if not self._slot.acquire(blocking=False):
                raise RuntimeError("Reranker capacity busy; use fusion fallback.")
            try:
                model = self._model or self._load()
                return model.predict(pairs)
            finally:
                self._slot.release()

        try:
            scores = await asyncio.wait_for(
                asyncio.to_thread(predict), timeout=self.timeout_seconds
            )
        except TimeoutError as exc:
            raise RerankerTimeoutError("Reranker timed out; caller falls back to fusion.") from exc
        if len(scores) != len(candidates) or not all(math.isfinite(float(x)) for x in scores):
            raise RuntimeError("Reranker returned invalid scores; use fusion fallback.")
        ranked = sorted(
            zip(candidates, scores, strict=False), key=lambda pair: float(pair[1]), reverse=True
        )
        return [hit for hit, _ in ranked[:top_n]]
