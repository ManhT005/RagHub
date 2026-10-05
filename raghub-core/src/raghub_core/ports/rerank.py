from dataclasses import dataclass
from typing import Protocol

from raghub_core.domain.providers.contracts import RerankProvider
from raghub_core.domain.retrieval.models import RetrievalScope


@dataclass(frozen=True)
class RerankRuntime:
    provider: RerankProvider
    candidate_limit: int = 40
    top_n: int = 8
    timeout_seconds: float = 5


class RerankResolverPort(Protocol):
    async def resolve_rerank(self, scope: RetrievalScope) -> RerankRuntime | None: ...
