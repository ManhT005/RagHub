import asyncio
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


@celery_app.task(bind=True, max_retries=3, name="documents.ingest_version")
def ingest_document_version(self: Task, document_version_id: str) -> None:
    try:
        asyncio.run(
            _process_document_version(
                uuid.UUID(document_version_id),
                retries=self.request.retries,
                max_retries=self.max_retries,
            )
        )
    except IngestionError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=min(60, 2 ** (self.request.retries + 1))) from exc
        raise
