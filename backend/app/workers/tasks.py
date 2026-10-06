import asyncio
import re
import uuid

from celery import Task
from raghub_core.domain.ingestion.errors import IngestionError as IngestionError

from app.delivery.workers.ingestion import (
    _process_document_version as _process_document_version,
)
from app.delivery.workers.ingestion import (
    _record_failure as _record_failure,
)
from app.delivery.workers.ingestion import (
    _run_attempt as _run_attempt,
)
from app.delivery.workers.ingestion import (
    _run_pipeline as _run_pipeline,
)
from app.delivery.workers.ingestion import (
    _set_stage as _set_stage,
)
from app.infrastructure.task_queue.celery_app import celery_app

QUOTA_WAIT_CODES = frozenset({"EMBEDDING_QUOTA_WAIT", "EMBEDDING_QUOTA_UNAVAILABLE"})
QUOTA_MAX_RETRIES = 48
QUOTA_RETRY_COUNTDOWN = 120


def quota_retry_plan(exc: IngestionError, retries: int) -> tuple[float, int] | None:
    """Long patient retries for quota waits; None defers to the default policy."""
    message = str(exc)
    rate_limited = "rate limit" in message.lower() or "429" in message
    if exc.code in QUOTA_WAIT_CODES or (exc.code == "EMBEDDING_FAILED" and rate_limited):
        wait = QUOTA_RETRY_COUNTDOWN
        match = re.search(r"retry after ([0-9]+(?:\.[0-9]+)?)s", message)
        if match:
            wait = min(600.0, max(30.0, float(match.group(1))))
        if retries < QUOTA_MAX_RETRIES:
            return wait, QUOTA_MAX_RETRIES
    return None


@celery_app.task(bind=True, max_retries=3, name="documents.ingest_version")
def ingest_document_version(self: Task, document_version_id: str) -> dict[str, object]:
    try:
        return asyncio.run(
            _process_document_version(
                uuid.UUID(document_version_id),
                retries=self.request.retries,
                max_retries=self.max_retries,
            )
        )
    except IngestionError as exc:
        plan = quota_retry_plan(exc, self.request.retries)
        if plan is not None:
            countdown, max_retries = plan
            raise self.retry(
                exc=exc, countdown=countdown, max_retries=max_retries, priority=2
            ) from exc
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc, countdown=min(60, 2 ** (self.request.retries + 1)), priority=2
            ) from exc
        raise
