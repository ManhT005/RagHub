from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "raghub",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks",
        "app.workers.reindex_tasks",
        "app.workers.provider_tasks",
        "app.workers.embedding_tasks",
    ],
)
celery_app.conf.update(
    task_routes={
        "documents.ingest_version": {
            "queue": "rag-ocr" if settings.rag_ocr_enabled else "rag-ingestion",
            "priority": 1,
        },
        "providers.reindex_workspace": {
            "queue": "rag-ocr" if settings.rag_ocr_enabled else "rag-reindex",
            "priority": 3,
        },
        "embedding.process_work_item_batch": {"queue": "rag-embedding"},
        "providers.local_download": {"priority": 4},
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_default_priority=2,
    task_queue_max_priority=4,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    # Pull jobs can run for two hours; do not redeliver them after Redis's 1h default.
    broker_transport_options={"visibility_timeout": 7500, "priority_steps": [0, 1, 2, 3, 4]},
    result_backend_transport_options={"visibility_timeout": 7500},
    visibility_timeout=7500,
)
