from uuid import UUID

from app.core_domain.documents.upload import UploadReceipt
from app.core_domain.errors import AppError
from app.core_domain.ingestion.errors import RETRYABLE_ERROR_CODES
from app.core_domain.retrieval.models import RetrievalScope
from app.ports.documents import DocumentRetryRepositoryPort
from app.ports.task_queue import TaskQueuePort


class RetryDocumentUseCase:
    def __init__(self, repository: DocumentRetryRepositoryPort, queue: TaskQueuePort) -> None:
        self.repository, self.queue = repository, queue

    async def execute(
        self, scope: RetrievalScope, version_id: UUID, *, reindex: bool = False
    ) -> UploadReceipt:
        state = await self.repository.load_for_retry(scope, version_id)
        if state is None:
            raise AppError(
                "DOCUMENT_VERSION_NOT_FOUND", "Document version was not found.", status_code=404
            )
        expected = "READY" if reindex else "FAILED"
        if state.receipt.status != expected:
            message = (
                "Only ready versions can be re-indexed."
                if reindex
                else "Only failed versions can be retried."
            )
            raise AppError("INVALID_DOCUMENT_STATUS", message, status_code=409)
        if not reindex and state.error_code not in RETRYABLE_ERROR_CODES:
            raise AppError(
                "DOCUMENT_NOT_RETRYABLE",
                "This failure cannot be retried. Correct the document and upload it again.",
                status_code=409,
            )
        if not await self.repository.try_retry_lock(version_id):
            raise AppError(
                "INGESTION_IN_PROGRESS", "Ingestion is still finishing.", status_code=409
            )
        receipt = await self.repository.reset(version_id)
        await self.repository.commit()
        try:
            self.queue.enqueue_ingestion(version_id)
        except Exception as exc:
            await self.repository.mark_queue_failure(version_id, str(exc))
            await self.repository.commit()
            message = "Could not queue re-indexing." if reindex else "Could not queue ingestion."
            raise AppError("QUEUE_UNAVAILABLE", message, status_code=503) from exc
        return receipt
