from uuid import UUID

from app.ports.documents import DocumentRetryRepositoryPort
from app.ports.task_queue import TaskQueuePort
from raghub_core.domain.documents.upload import UploadReceipt
from raghub_core.domain.errors import CoreError
from raghub_core.domain.ingestion.errors import RETRYABLE_ERROR_CODES
from raghub_core.domain.retrieval.models import RetrievalScope


class RetryDocumentUseCase:
    def __init__(self, repository: DocumentRetryRepositoryPort, queue: TaskQueuePort) -> None:
        self.repository, self.queue = repository, queue

    async def execute(
        self, scope: RetrievalScope, version_id: UUID, *, reindex: bool = False
    ) -> UploadReceipt:
        state = await self.repository.load_for_retry(scope, version_id)
        if state is None:
            raise CoreError("DOCUMENT_VERSION_NOT_FOUND", "Document version was not found.")
        expected = "READY" if reindex else "FAILED"
        if state.receipt.status != expected:
            message = (
                "Only ready versions can be re-indexed."
                if reindex
                else "Only failed versions can be retried."
            )
            raise CoreError("INVALID_DOCUMENT_STATUS", message)
        if not reindex and state.error_code not in RETRYABLE_ERROR_CODES:
            raise CoreError(
                "DOCUMENT_NOT_RETRYABLE",
                "This failure cannot be retried. Correct the document and upload it again.",
            )
        if not await self.repository.try_retry_lock(version_id):
            raise CoreError("INGESTION_IN_PROGRESS", "Ingestion is still finishing.")
        receipt = await self.repository.reset(version_id)
        await self.repository.commit()
        try:
            self.queue.enqueue_ingestion(version_id)
        except Exception as exc:
            await self.repository.mark_queue_failure(version_id, str(exc))
            await self.repository.commit()
            message = "Could not queue re-indexing." if reindex else "Could not queue ingestion."
            raise CoreError("QUEUE_UNAVAILABLE", message) from exc
        return receipt
