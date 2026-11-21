"""Pinned Qwen3 causal reranking; offline runtime, no generated answers."""

import asyncio
import logging
import math
import re
import threading
from functools import lru_cache
from pathlib import Path

from raghub_core.ports.reranker import RerankerTimeoutError

from app.infrastructure.ai.local_reranker import snapshot_sha256

MODEL_ID = "Qwen/Qwen3-Reranker-0.6B"
MODEL_REVISION = "e61197ed45024b0ed8a2d74b80b4d909f1255473"
INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"
PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query "
    'and the Instruct provided. Note that the answer can only be "yes" or "no".'
    "<|im_end|>\n<|im_start|>user\n"
)
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
MAX_LENGTH = 1024
BATCH_SIZE = 2
logger = logging.getLogger(__name__)


class QwenReranker:
    def __init__(self, snapshot_path, expected_sha256, timeout_seconds):
        self.snapshot_path = snapshot_path
        self.expected_sha256 = expected_sha256
        self.timeout_seconds = timeout_seconds
        self._slot = threading.Lock()
        self._model = None
        self._tokenizer = None

    def _load(self):
        snapshot = Path(self.snapshot_path)
        if not re.fullmatch(r"[0-9a-f]{64}", self.expected_sha256):
            raise RuntimeError("Qwen reranker checksum is not pinned")
        if snapshot_sha256(snapshot) != self.expected_sha256:
            raise RuntimeError("Qwen reranker snapshot checksum mismatch")
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(
            str(snapshot), padding_side="left", local_files_only=True, trust_remote_code=False
        )
        model = AutoModelForCausalLM.from_pretrained(
            str(snapshot),
            local_files_only=True,
            trust_remote_code=False,
            dtype=torch.float32,
        ).eval()
        # CPU deployment: dynamic INT8 reduces linear-layer memory and compute.
        # Quantization is local and deterministic; the downloaded snapshot stays intact.
        torch.ao.quantization.quantize_dynamic(
            model, {torch.nn.Linear}, dtype=torch.qint8, inplace=True
        )
        self._prefix = self._tokenizer.encode(PREFIX, add_special_tokens=False)
        self._suffix = self._tokenizer.encode(SUFFIX, add_special_tokens=False)
        self._yes = self._tokenizer.convert_tokens_to_ids("yes")
        self._no = self._tokenizer.convert_tokens_to_ids("no")
        if self._yes == self._no or self._yes is None or self._no is None:
            raise RuntimeError("Qwen reranker label tokens are invalid")
        self._model = model
        return self._model

    def warmup(self):
        """Best-effort preload after binding; requests retain hybrid fallback."""
        if not self._slot.acquire(blocking=False):
            return
        try:
            if self._model is None:
                self._load()
        except Exception:
            logger.warning("qwen_reranker_warmup_failed")
        finally:
            self._slot.release()

    def _inputs(self, query, documents):
        texts = [
            f"<Instruct>: {INSTRUCTION}\n<Query>: {query}\n<Document>: {doc}" for doc in documents
        ]
        encoded = self._tokenizer(
            texts,
            padding=False,
            truncation=True,
            add_special_tokens=False,
            max_length=MAX_LENGTH - len(self._prefix) - len(self._suffix),
        )
        encoded["input_ids"] = [self._prefix + ids + self._suffix for ids in encoded["input_ids"]]
        # Rebuild attention masks after adding the mandatory prefix/suffix.
        encoded.pop("attention_mask", None)
        return self._tokenizer.pad(encoded, padding=True, return_tensors="pt")

    def _predict(self, query, documents, cancelled):
        import torch

        if not self._slot.acquire(blocking=False):
            raise RuntimeError("Qwen reranker capacity busy; use fusion fallback")
        try:
            model = self._model or self._load()
            scores = []
            with torch.inference_mode():
                for start in range(0, len(documents), BATCH_SIZE):
                    if cancelled.is_set():
                        raise RerankerTimeoutError("Qwen reranker cancelled")
                    inputs = self._inputs(query, documents[start : start + BATCH_SIZE])
                    # Qwen3 supports logits_to_keep: avoid allocating a vocabulary
                    # distribution for every position when only the last is scored.
                    logits = model(**inputs, logits_to_keep=1, use_cache=False).logits[:, -1, :]
                    pair = torch.stack([logits[:, self._no], logits[:, self._yes]], dim=1)
                    scores.extend(torch.softmax(pair.float(), dim=1)[:, 1].tolist())
            return scores
        finally:
            self._slot.release()

    async def scores(self, query, documents):
        if not documents:
            return []
        cancelled = threading.Event()
        try:
            values = await asyncio.wait_for(
                asyncio.to_thread(self._predict, query, documents, cancelled), self.timeout_seconds
            )
        except TimeoutError as exc:
            raise RerankerTimeoutError("Qwen reranker timed out; use fusion fallback") from exc
        finally:
            # A timed-out CPU batch cannot be killed, but later batches must stop.
            cancelled.set()
        if len(values) != len(documents) or not all(math.isfinite(float(v)) for v in values):
            raise RuntimeError("Qwen reranker returned invalid scores")
        return values


@lru_cache(maxsize=2)
def qwen_reranker(snapshot_path, expected_sha256, timeout_seconds):
    return QwenReranker(snapshot_path, expected_sha256, timeout_seconds)
