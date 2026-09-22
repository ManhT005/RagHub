import asyncio
import uuid

from celery import Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.infrastructure.elasticsearch.chunks import ChunkIndexer
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.task_queue.celery_app import celery_app
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion, IngestionJob
from app.modules.ingestion.chunker import chunk_sections
from app.modules.ingestion.embedder import embed_chunks
from app.modules.ingestion.parser import (
    EmptyExtractedTextError,
    InvalidPdfError,
    TextDecodeError,
    UnsupportedFileTypeError,
    UnsupportedOcrError,
    parse_document,
)


class IngestionError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


async def _set_stage(
    session: AsyncSession,
    document: Document,
    version: DocumentVersion,
    job: IngestionJob,
    stage: DocumentStatus,
    progress: int,
) -> None:
    document.status = version.status = job.stage = stage
    job.progress = progress
    await session.commit()


async def _update_job(
    version_id: uuid.UUID,
    *,
    code: str | None = None,
    message: str | None = None,
    attempts: int,
    failed: bool = False,
) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            version = await session.get(DocumentVersion, version_id)
            if version is None:
                return
            job = await session.scalar(
                select(IngestionJob).where(IngestionJob.document_version_id == version_id)
            )
            document = await session.get(Document, version.document_id)
            if job:
                job.attempts = attempts
                job.error_code = code
                job.error_message = message[:2000] if message else None
                if failed:
                    job.stage = DocumentStatus.FAILED
            if failed:
                version.status = DocumentStatus.FAILED
                if document:
                    document.status = DocumentStatus.FAILED
            await session.commit()
    finally:
        await engine.dispose()


async def _process_document_version(version_id: uuid.UUID) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            version = await session.get(DocumentVersion, version_id)
            if version is None:
                raise IngestionError(
                    "INGESTION_FAILED", "Document version does not exist.", retryable=False
                )
            document = await session.get(Document, version.document_id)
            job = await session.scalar(
                select(IngestionJob).where(IngestionJob.document_version_id == version_id)
            )
            if document is None or job is None:
                raise IngestionError(
                    "INGESTION_FAILED", "Ingestion metadata is incomplete.", retryable=False
                )
            if version.status == DocumentStatus.READY:
                return
            await _set_stage(session, document, version, job, DocumentStatus.PARSING, 20)
            try:
                content = MinioObjectStorage(settings).get(version.storage_key)
            except Exception as exc:
                raise IngestionError("STORAGE_UNAVAILABLE", str(exc), retryable=True) from exc
            try:
                sections = parse_document(content, document.name)
            except InvalidPdfError as exc:
                raise IngestionError("INVALID_PDF", str(exc), retryable=False) from exc
            except UnsupportedOcrError as exc:
                raise IngestionError("FAILED_UNSUPPORTED_OCR", str(exc), retryable=False) from exc
            except TextDecodeError as exc:
                raise IngestionError("TEXT_DECODE_FAILED", str(exc), retryable=False) from exc
            except EmptyExtractedTextError as exc:
                raise IngestionError("EMPTY_EXTRACTED_TEXT", str(exc), retryable=False) from exc
            except UnsupportedFileTypeError as exc:
                raise IngestionError("UNSUPPORTED_FILE_TYPE", str(exc), retryable=False) from exc
            except Exception as exc:
                raise IngestionError("PARSE_FAILED", str(exc), retryable=False) from exc
            await _set_stage(session, document, version, job, DocumentStatus.CHUNKING, 45)
            try:
                chunks = chunk_sections(sections, version.id)
                if not chunks:
                    raise EmptyExtractedTextError("No chunks were extracted.")
            except EmptyExtractedTextError as exc:
                raise IngestionError("EMPTY_EXTRACTED_TEXT", str(exc), retryable=False) from exc
            except Exception as exc:
                raise IngestionError("CHUNKING_FAILED", str(exc), retryable=False) from exc
            await _set_stage(session, document, version, job, DocumentStatus.EMBEDDING, 65)
            try:
                embeddings = embed_chunks(chunks)
            except Exception as exc:
                raise IngestionError("EMBEDDING_FAILED", str(exc), retryable=False) from exc
            await _set_stage(session, document, version, job, DocumentStatus.INDEXING, 85)
            try:
                indexer = ChunkIndexer(settings)
                try:
                    indexer.replace_document_version(
                        organization_id=version.organization_id,
                        workspace_id=version.workspace_id,
                        document_id=document.id,
                        document_version_id=version.id,
                        source_name=document.name,
                        chunks=chunks,
                        embeddings=embeddings,
                    )
                finally:
                    indexer.close()
            except Exception as exc:
                raise IngestionError("INDEX_UNAVAILABLE", str(exc), retryable=True) from exc
            job.error_code = job.error_message = job.error_details = None
            await _set_stage(session, document, version, job, DocumentStatus.READY, 100)
    finally:
        await engine.dispose()


@celery_app.task(bind=True, max_retries=3, name="documents.ingest_version")
def ingest_document_version(self: Task, document_version_id: str) -> None:
    version_id = uuid.UUID(document_version_id)
    attempt = self.request.retries + 1
    asyncio.run(_update_job(version_id, attempts=attempt))
    try:
        asyncio.run(_process_document_version(version_id))
    except IngestionError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            asyncio.run(_update_job(version_id, code=exc.code, message=str(exc), attempts=attempt))
            raise self.retry(exc=exc, countdown=min(60, 2**attempt)) from exc
        asyncio.run(
            _update_job(version_id, code=exc.code, message=str(exc), attempts=attempt, failed=True)
        )
        raise
    except Exception as exc:
        asyncio.run(
            _update_job(
                version_id, code="INGESTION_FAILED", message=str(exc), attempts=attempt, failed=True
            )
        )
        raise
