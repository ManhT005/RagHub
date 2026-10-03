from typing import Protocol

from app.core_domain.retrieval.models import RetrievalScope, RetrievedChunk


class DocumentReadinessPort(Protocol):
    async def filter_ready(
        self, scope: RetrievalScope, hits: list[RetrievedChunk]
    ) -> list[RetrievedChunk]: ...


class RetrievalPort(Protocol):
    async def retrieve(
        self, scope: RetrievalScope, query: str, limit: int
    ) -> list[RetrievedChunk]: ...
