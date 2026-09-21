import asyncio
import uuid
from pathlib import Path

from celery import Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.infrastructure.elasticsearch.chunks import ChunkIndexer
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.task_queue.celery_app import celery_app
from app.modules.documents.models import (
    Document,
    DocumentStatus,
    DocumentVersion,
    IngestionJob,
)
from app.modules.ingestion.chunker import chunk_pages
from app.modules.ingestion.parser import InvalidPdfError, UnsupportedOcrError, parse_pdf

NON_RETRYABLE_ERRORS = (InvalidPdfError, UnsupportedOcrError)


async def _set_stage(
    session: AsyncSession,
    *,
    document: Document,
    version: DocumentVersion,
    job: IngestionJob,
    stage: DocumentStatus,
    progress: int,
) -> None:
    document.status = stage
    version.status = stage
    job.stage = stage
    job.progress = progress
    await session.commit()


async def _mark_failed(
    version_id: uuid.UUID,
    *,
    code: str,
    message: str,
    attempts: int,
) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            version = await session.get(DocumentVersion, version_id)
            if version is None:
                return
            document = await session.get(Document, version.document_id)
            job = await session.scalar(
                select(IngestionJob).where(IngestionJob.document_version_id == version_id)
            )
            version.status = DocumentStatus.FAILED
            if document is not None:
                document.status = DocumentStatus.FAILED
            if job is not None:
                job.stage = DocumentStatus.FAILED
                job.error_code = code
                job.error_message = message[:2000]
                job.attempts = attempts
            await session.commit()
    finally:
        await engine.dispose()


async def _process_document_version(version_id: uuid.UUID) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            version = await session.get(DocumentVersion, version_id)
            if version is None:
                raise InvalidPdfError(f"Document version {version_id} does not exist.")
            document = await session.get(Document, version.document_id)
            job = await session.scalar(
                select(IngestionJob).where(IngestionJob.document_version_id == version_id)
            )
            if document is None or job is None:
                raise InvalidPdfError("Document ingestion metadata is incomplete.")

            await _set_stage(
                session,
                document=document,
                version=version,
                job=job,
                stage=DocumentStatus.PARSING,
                progress=20,
            )
            content = MinioObjectStorage(settings).get(version.storage_key)
            pages = parse_pdf(content)

            await _set_stage(
                session,
                document=document,
                version=version,
                job=job,
                stage=DocumentStatus.CHUNKING,
                progress=50,
            )
            chunks = chunk_pages(pages, version.id)

            await _set_stage(
                session,
                document=document,
                version=version,
                job=job,
                stage=DocumentStatus.INDEXING,
                progress=75,
            )
            indexer = ChunkIndexer(settings)
            try:
                indexer.replace_document_version(
                    organization_id=version.organization_id,
                    workspace_id=version.workspace_id,
                    document_id=document.id,
                    document_version_id=version.id,
                    source_name=Path(document.name).name,
                    chunks=chunks,
                )
            finally:
                indexer.close()

            job.error_code = None
            job.error_message = None
            await _set_stage(
                session,
                document=document,
                version=version,
                job=job,
                stage=DocumentStatus.READY,
                progress=100,
            )
    finally:
        await engine.dispose()


@celery_app.task(bind=True, max_retries=3, name="documents.ingest_version")
def ingest_document_version(self: Task, document_version_id: str) -> None:
    version_id = uuid.UUID(document_version_id)
    try:
        asyncio.run(_process_document_version(version_id))
    except NON_RETRYABLE_ERRORS as exc:
        asyncio.run(
            _mark_failed(
                version_id,
                code="FAILED_UNSUPPORTED_OCR"
                if isinstance(exc, UnsupportedOcrError)
                else "INVALID_PDF",
                message=str(exc),
                attempts=self.request.retries + 1,
            )
        )
        raise
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=min(60, 2 ** (self.request.retries + 1))) from exc
        asyncio.run(
            _mark_failed(
                version_id,
                code="INGESTION_FAILED",
                message=str(exc),
                attempts=self.request.retries + 1,
            )
        )
        raise
