from dataclasses import dataclass
from uuid import UUID

from app.core_domain.errors import CoreError
from app.core_domain.ingestion.errors import IngestionError
from app.core_domain.providers.errors import (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.core_domain.retrieval.models import RetrievalScope


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
