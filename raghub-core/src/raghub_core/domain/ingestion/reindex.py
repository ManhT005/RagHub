from dataclasses import dataclass
from uuid import UUID

from raghub_core.domain.errors import CoreError
from raghub_core.domain.ingestion.errors import IngestionError
from raghub_core.domain.providers.errors import (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from raghub_core.domain.retrieval.models import RetrievalScope


@dataclass(frozen=True)
class ReindexTarget:
    job_id: UUID
    scope: RetrievalScope
    index_version_id: UUID
    status: str
    current: bool


def has_all_document_versions(expected: set[UUID], indexed: set[UUID]) -> bool:
    return expected.issubset(indexed)


def is_transient_failure(exc: Exception) -> bool:
    if isinstance(exc, IngestionError):
        return exc.retryable
    if isinstance(
        exc,
        ProviderTimeoutError
        | ProviderUnavailableError
        | ProviderRateLimitError
        | ConnectionError
        | TimeoutError,
    ):
        return True
    return isinstance(exc, CoreError) and exc.code in {
        "STORAGE_UNAVAILABLE",
        "QUEUE_UNAVAILABLE",
        "SEARCH_UNAVAILABLE",
        "INDEX_UNAVAILABLE",
    }
