"""Concurrency regressions against PostgreSQL, not mocked locks or SQLite."""

import asyncio
import os
import uuid
from unittest.mock import Mock

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import Settings
from app.core.exceptions import AppError
from app.infrastructure.ingestion_lock import try_ingestion_lock
from app.modules.documents.models import DocumentStatus, DocumentVersion, IngestionJob
from app.modules.documents.repository import DocumentRepository
from app.modules.documents.service import DocumentService
from app.modules.organizations.models import Organization
from app.modules.workspaces.models import Workspace
from app.workers import tasks

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def database(monkeypatch: pytest.MonkeyPatch):
    url = os.getenv("RAGHUB_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set RAGHUB_TEST_DATABASE_URL to a migrated PostgreSQL database.")
    settings = Settings(_env_file=None, database_url=url)
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    engine = create_async_engine(url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    async with sessions() as session:
        session.add(
            Organization(id=organization_id, name="Concurrency test", slug=uuid.uuid4().hex)
        )
        await session.flush()
        session.add(
            Workspace(id=workspace_id, organization_id=organization_id, name="Test", slug="test")
        )
        await session.flush()
        _, version, _ = await DocumentRepository(session).create_upload(
            organization_id=organization_id,
            workspace_id=workspace_id,
            filename="test.txt",
            storage_key=str(uuid.uuid4()),
            checksum="0" * 64,
            mime_type="text/plain",
            size_bytes=5,
        )
        version_id = version.id
        await session.commit()
    try:
        yield engine, sessions, organization_id, workspace_id, version_id
    finally:
        async with sessions() as session:
            await session.execute(delete(Organization).where(Organization.id == organization_id))
            await session.commit()
        await engine.dispose()


async def test_duplicate_workers_and_ready_redelivery(database, monkeypatch: pytest.MonkeyPatch):
    _, sessions, _, _, version_id = database
    entered, release = asyncio.Event(), asyncio.Event()
    executions = []

    async def pipeline(session, document, version, job):
        executions.append(version.id)
        await tasks._set_stage(session, document, version, job, DocumentStatus.CHUNKING, 45)
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=15)
        await tasks._set_stage(session, document, version, job, DocumentStatus.READY, 100)

    monkeypatch.setattr(tasks, "_run_pipeline", pipeline)
    first = asyncio.create_task(tasks._process_document_version(version_id))
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        await asyncio.wait_for(tasks._process_document_version(version_id), timeout=5)
        async with sessions() as session:
            job = await session.scalar(
                select(IngestionJob).where(IngestionJob.document_version_id == version_id)
            )
            assert job.attempts == 1 and job.stage == "CHUNKING"
    finally:
        release.set()
        await first
    await tasks._process_document_version(version_id)
    async with sessions() as session:
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        assert job.attempts == 1 and job.stage == "READY" and job.progress == 100
    assert executions == [version_id]


async def test_lock_released_after_failure_and_transient_retry_succeeds(database, monkeypatch):
    _, sessions, _, _, version_id = database
    executions = []

    async def pipeline(session, document, version, job):
        executions.append(version.id)
        if len(executions) == 1:
            raise tasks.IngestionError(
                "STORAGE_UNAVAILABLE", "host=private.internal password=secret", retryable=True
            )
        await tasks._set_stage(session, document, version, job, DocumentStatus.READY, 100)

    monkeypatch.setattr(tasks, "_run_pipeline", pipeline)
    with pytest.raises(tasks.IngestionError):
        await tasks._process_document_version(version_id)
    async with sessions() as session:
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        assert job.error_code == "STORAGE_UNAVAILABLE" and job.attempts == 1
        assert "private.internal" not in job.error_message
    await tasks._process_document_version(version_id, retries=1)
    async with sessions() as session:
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        assert job.stage == "READY" and job.attempts == 2
        assert job.error_code is None


async def test_concurrent_manual_retries_enqueue_once(database, monkeypatch):
    _, sessions, organization_id, workspace_id, version_id = database
    async with sessions() as session:
        version = await session.get(DocumentVersion, version_id)
        version.status = "FAILED"
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        job.stage, job.error_code, job.attempts = "FAILED", "INDEX_UNAVAILABLE", 4
        await session.commit()
    queued = Mock()
    monkeypatch.setattr(tasks.ingest_document_version, "delay", queued)

    async def retry_request():
        async with sessions() as session:
            return await DocumentService(session).retry(organization_id, workspace_id, version_id)

    results = await asyncio.wait_for(
        asyncio.gather(retry_request(), retry_request(), return_exceptions=True), timeout=10
    )
    accepted = [result for result in results if not isinstance(result, Exception)]
    conflicts = [result for result in results if isinstance(result, AppError)]
    assert len(accepted) == len(conflicts) == 1, results
    assert accepted[0].status == "QUEUED" and conflicts[0].status_code == 409
    queued.assert_called_once_with(str(version_id))
    async with sessions() as session:
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        assert job.attempts == job.progress == 0 and job.error_code is None


async def test_foreign_retry_and_active_worker_lock_are_rejected(database, monkeypatch):
    engine, sessions, organization_id, workspace_id, version_id = database
    async with sessions() as session:
        version = await session.get(DocumentVersion, version_id)
        version.status = "FAILED"
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        job.stage, job.error_code = "FAILED", "INDEX_UNAVAILABLE"
        await session.commit()
    queued = Mock()
    monkeypatch.setattr(tasks.ingest_document_version, "delay", queued)
    async with sessions() as session:
        with pytest.raises(AppError) as error:
            await DocumentService(session).retry(uuid.uuid4(), workspace_id, version_id)
        assert error.value.status_code == 404
    async with engine.connect() as connection:
        async with try_ingestion_lock(connection, version_id) as acquired:
            assert acquired
            async with sessions() as session:
                with pytest.raises(AppError) as error:
                    await DocumentService(session).retry(organization_id, workspace_id, version_id)
                assert error.value.code == "INGESTION_IN_PROGRESS"
    queued.assert_not_called()


@pytest.mark.parametrize("retryable,code", [(True, "INDEX_UNAVAILABLE"), (False, "INVALID_PDF")])
async def test_final_failure_is_saved_before_unlock(database, monkeypatch, retryable, code):
    _, sessions, _, _, version_id = database
    async with sessions() as session:
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        job.attempts = 3 if retryable else 0
        await session.commit()

    async def fail(*args):
        raise tasks.IngestionError(code, "private.internal", retryable=retryable)

    monkeypatch.setattr(tasks, "_run_pipeline", fail)
    with pytest.raises(tasks.IngestionError):
        await tasks._process_document_version(version_id, retries=3 if retryable else 0)
    async with sessions() as session:
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_version_id == version_id)
        )
        version = await session.get(DocumentVersion, version_id)
        assert job.stage == version.status == "FAILED"
        assert job.attempts == (4 if retryable else 1)
        assert job.error_code == code and "private.internal" not in job.error_message
