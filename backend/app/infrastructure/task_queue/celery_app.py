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
PROVIDER_QUEUE = "rag-provider"
INGESTION_QUEUE = "rag-ocr" if settings.rag_ocr_enabled else "rag-ingestion"
REINDEX_QUEUE = "rag-ocr" if settings.rag_ocr_enabled else "rag-reindex"
# Queues served by the user-facing RAG worker; provider jobs never share its slots.
RAG_WORKER_QUEUES = ("rag-ingestion", "rag-embedding", "rag-reindex")

celery_app.conf.update(
    task_routes={
        "documents.ingest_version": {"queue": INGESTION_QUEUE, "priority": 1},
        "embedding.process_work_item_batch": {"queue": "rag-embedding", "priority": 2},
        "providers.reindex_workspace": {"queue": REINDEX_QUEUE, "priority": 3},
        # Long-running model management runs on the dedicated provider worker.
        "providers.bootstrap_health": {"queue": PROVIDER_QUEUE, "priority": 1},
        "providers.local_download": {"queue": PROVIDER_QUEUE, "priority": 4},
        "providers.ollama_pull": {"queue": PROVIDER_QUEUE, "priority": 4},
    },
    # Used when `--concurrency` is not passed (RAG worker); explicit ENV > preset > default.
    worker_concurrency=settings.rag_worker_concurrency,
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
    broker_transport_options={"visibility_timeout": 7500, "priority_steps": [0, 1, 2, 3, 4, 6, 9]},
    result_backend_transport_options={"visibility_timeout": 7500},
    visibility_timeout=7500,
)
