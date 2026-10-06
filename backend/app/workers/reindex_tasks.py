import asyncio
import uuid

from celery import Task

from app.delivery.workers.reindex import (
    _has_all_document_versions as _has_all_document_versions,
)
from app.delivery.workers.reindex import (
    _is_current_target as _is_current_target,
)
from app.delivery.workers.reindex import (
    _is_transient_error as _is_transient_error,
)
from app.delivery.workers.reindex import (
    _reset_attempt_progress as _reset_attempt_progress,
)
from app.delivery.workers.reindex import (
    _run_reindex as _run_reindex,
)
from app.infrastructure.task_queue.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3, name="providers.reindex_workspace")
def reindex_workspace(self: Task, job_id: str) -> None:
    try:
        asyncio.run(
            _run_reindex(uuid.UUID(job_id), fail_transient=self.request.retries >= self.max_retries)
        )
    except Exception as exc:
        if _is_transient_error(exc) and self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc, countdown=min(60, 2 ** (self.request.retries + 1)), priority=2
            ) from exc
        raise
