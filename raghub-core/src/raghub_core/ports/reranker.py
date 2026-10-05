"""Optional reranker port: local cross-encoder with fusion fallback."""
from __future__ import annotations

from typing import Protocol

from raghub_core.domain.retrieval.models import RetrievedChunk


class RerankerTimeoutError(Exception):
    pass


class RerankerPort(Protocol):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        """Return at most top_n candidates ordered by relevance; raise on timeout."""
        ...
