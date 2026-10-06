"""Real Redis/Celery consumers and PostgreSQL ingestion; no model downloads.

Set RAGHUB_TEST_REDIS_URL and RAGHUB_TEST_DATABASE_URL to disposable services.
Queues are namespaced and database entities live in an isolated test schema.
"""

import asyncio
import os
import time
import uuid
from threading import Event

import pytest
from celery import Celery
from celery.contrib.testing.worker import start_worker
from celery.result import allow_join_result
from kombu import Queue
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.delivery.workers import ingestion as ingestion_runtime
from app.infrastructure.task_queue.celery_app import PROVIDER_QUEUE, RAG_WORKER_QUEUES, celery_app
from app.modules.documents.models import DocumentStatus, IngestionJob
from app.modules.documents.repository import DocumentRepository
from app.modules.organizations.models import Organization
from app.modules.workspaces.models import Workspace
from app.workers import tasks

pytestmark = pytest.mark.integration


async def test_busy_provider_worker_does_not_starve_ingestion(isolated_sessions, monkeypatch):
    redis_url = os.getenv("RAGHUB_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("Set RAGHUB_TEST_REDIS_URL to run worker starvation regression.")
    async with isolated_sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
        organization = Organization(name="Worker isolation", slug=uuid.uuid4().hex)
        session.add(organization)
        await session.flush()
        workspace = Workspace(organization_id=organization.id, name="Test", slug="test")
        session.add(workspace)
        await session.flush()
        _, version, _ = await DocumentRepository(session).create_upload(
            organization_id=organization.id,
            workspace_id=workspace.id,
            filename="test.pdf",
            storage_key=uuid.uuid4().hex,
            checksum="0" * 64,
            mime_type="application/pdf",
            size_bytes=10,
        )
        version_id = version.id
        await session.commit()

    settings = Settings(_env_file=None, database_url=os.environ["RAGHUB_TEST_DATABASE_URL"])
    monkeypatch.setattr(ingestion_runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(
        ingestion_runtime,
        "create_async_engine",
        lambda url, **kwargs: create_async_engine(
            url, connect_args={"server_settings": {"search_path": schema}}, **kwargs
        ),
    )

    async def model_free_pipeline(session, document, version, job):
        # Exercise real DB transitions under the production task and advisory lock.
        for stage, progress in (
            (DocumentStatus.CHUNKING, 45),
            (DocumentStatus.EMBEDDING, 65),
            (DocumentStatus.INDEXING, 85),
            (DocumentStatus.READY, 100),
        ):
            await tasks._set_stage(session, document, version, job, stage, progress)

    monkeypatch.setattr(ingestion_runtime, "_run_pipeline", model_free_pipeline)
    await asyncio.to_thread(run_workers, redis_url, version_id)
    async with isolated_sessions() as session:
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        assert job.stage == "READY" and job.progress == 100 and job.attempts == 1


def run_workers(redis_url, version_id):
    namespace = "worker-isolation-" + uuid.uuid4().hex + "-"
    app = Celery(namespace, broker=redis_url, backend=redis_url, set_as_current=False)
    app.conf.update(
        task_routes=celery_app.conf.task_routes,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        broker_transport_options={
            **celery_app.conf.broker_transport_options,
            "global_keyprefix": namespace,
        },
        result_backend_transport_options={"global_keyprefix": namespace},
        task_default_queue="celery",
    )
    provider_started, provider_release, provider_finished = Event(), Event(), Event()

    @app.task(name="tests.provider_sleep", shared=False)
    def provider_sleep():
        provider_started.set()
        try:
            if not provider_release.wait(30):
                raise TimeoutError("Ingestion failed to finish while the provider was busy")
            return "released"
        finally:
            provider_finished.set()

    # Keep the production Celery entrypoint, result serialization and ingestion lock.
    app.task(name="documents.ingest_version", shared=False)(tasks.ingest_document_version.run)
    app.conf.task_routes = {
        **app.conf.task_routes,
        "tests.provider_sleep": {"queue": PROVIDER_QUEUE},
    }
    provider_result = ingestion_result = None
    try:
        with (
            start_worker(
                app,
                queues=(PROVIDER_QUEUE, "celery"),
                concurrency=1,
                pool="solo",
                hostname="provider@" + namespace,
                perform_ping_check=False,
                shutdown_timeout=15,
            ) as provider_worker,
            start_worker(
                app,
                queues=RAG_WORKER_QUEUES,
                concurrency=1,
                pool="solo",
                hostname="rag@" + namespace,
                perform_ping_check=False,
                shutdown_timeout=15,
            ) as rag_worker,
        ):
            try:
                # Check actual consumers, not only the task route dictionary.
                assert {q.name for q in provider_worker.consumer.task_consumer.queues} == {
                    PROVIDER_QUEUE,
                    "celery",
                }
                assert {q.name for q in rag_worker.consumer.task_consumer.queues} == set(
                    RAG_WORKER_QUEUES
                )
                provider_result = provider_sleep.delay()
                assert provider_started.wait(5), "Provider task was not started"
                started = time.monotonic()
                # No explicit queue: the production ingestion route must work.
                ingestion_result = app.send_task("documents.ingest_version", args=[str(version_id)])
                with allow_join_result():
                    result = ingestion_result.get(timeout=5)
                assert time.monotonic() - started <= 5
                assert result["status"] == "READY" and result["processed"] is True
                assert not provider_finished.is_set(), "Provider finished before ingestion"
            finally:
                provider_release.set()
                if provider_result is not None:
                    with allow_join_result():
                        assert provider_result.get(timeout=5) == "released"
    finally:
        # Delete only this run's queues/results; never flush the shared Redis database.
        with app.connection() as connection:
            for name in (*RAG_WORKER_QUEUES, PROVIDER_QUEUE, "celery"):
                Queue(name, routing_key=name)(connection).delete()
        for result in (provider_result, ingestion_result):
            if result is not None:
                result.forget()
        app.close()
