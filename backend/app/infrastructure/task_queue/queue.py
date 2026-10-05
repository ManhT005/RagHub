from uuid import UUID


class CeleryTaskQueue:
    """Keep task imports lazy to avoid worker/composition import cycles."""

    def enqueue_ingestion(self, version_id: UUID) -> None:
        from app.workers.tasks import ingest_document_version

        ingest_document_version.delay(str(version_id))

    def enqueue_reindex(self, job_id: UUID) -> None:
        from app.workers.reindex_tasks import reindex_workspace

        reindex_workspace.delay(str(job_id))
