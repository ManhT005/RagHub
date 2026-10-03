from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class TaskQueuePort(Protocol):
    def enqueue_ingestion(self, version_id: UUID) -> None: ...
    def enqueue_reindex(self, job_id: UUID) -> None: ...
