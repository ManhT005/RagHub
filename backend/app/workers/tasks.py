import asyncio
import logging
import uuid

from celery import Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.infrastructure.elasticsearch.chunks import ChunkIndexer
from app.infrastructure.ingestion_lock import try_ingestion_lock
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.task_queue.celery_app import celery_app
from app.modules.ai_providers.resolver import ProviderResolver
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion, IngestionJob
from app.modules.ingestion.chunker import chunk_sections
from app.modules.ingestion.errors import IngestionError, ingestion_error_message
from app.modules.ingestion.parser import (
    EmptyExtractedTextError,
    InvalidPdfError,
    TextDecodeError,
    UnsupportedFileTypeError,
    UnsupportedOcrError,
    parse_document,
)

logger = logging.getLogger(__name__)


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


async def _record_failure(
    session: AsyncSession, version_id: uuid.UUID, error: IngestionError, *, failed: bool
) -> None:
    await session.rollback()
    version = await session.get(DocumentVersion, version_id)
    job = await session.scalar(
        select(IngestionJob).where(IngestionJob.document_version_id == version_id)
    )
    if version is None or job is None:
        return
    job.error_code = error.code
    job.error_message = ingestion_error_message(error.code)
    job.error_details = {"stage": job.stage, "retryable": error.retryable}
    if failed:
        document = await session.get(Document, version.document_id)
        version.status = job.stage = DocumentStatus.FAILED
        if document is not None:
            document.status = DocumentStatus.FAILED
    await session.commit()

async def _run_pipeline(
    session: AsyncSession, document: Document, version: DocumentVersion, job: IngestionJob
) -> None:
    settings = get_settings()
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
        resolved = await ProviderResolver(session).embedding_for_workspace(
            version.organization_id, version.workspace_id
        )
        vectors = await resolved.provider.embed_documents([chunk.content for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("Embedding response count does not match chunks")
        embeddings = {
            str(chunk.chunk_id): vector
            for chunk, vector in zip(chunks, vectors, strict=True)
        }
    except Exception as exc:
        raise IngestionError("EMBEDDING_FAILED", str(exc), retryable=False) from exc
    await _set_stage(session, document, version, job, DocumentStatus.INDEXING, 85)
    # Persist the version as READY before exposing its chunks to Elasticsearch.
    # Keep the document and job in INDEXING until bulk indexing completes, so the
    # API never reports a searchable document before its chunks are available.
    version.status = DocumentStatus.READY
    job.progress = 90
    await session.commit()
    indexer = ChunkIndexer(
        settings=settings,
        index_name=resolved.index_version.index_name,
        dimension=resolved.index_version.dimension,
    )
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
    except Exception as exc:
        try:
            indexer.delete_document_version(version.id)
        except Exception:
            logger.exception("Could not clean up failed index for version %s", version.id)
        raise IngestionError("INDEX_UNAVAILABLE", str(exc), retryable=True) from exc
    finally:
        indexer.close()
    job.error_code = job.error_message = job.error_details = None
    await _set_stage(session, document, version, job, DocumentStatus.READY, 100)


async def _run_attempt(
    session: AsyncSession, version_id: uuid.UUID, *, retries: int, max_retries: int
) -> None:
    version = await session.get(DocumentVersion, version_id)
    # READY remains resumable until the final Elasticsearch replacement commits.
    if version is None or version.status == DocumentStatus.FAILED:
        return
    job = await session.scalar(
        select(IngestionJob).where(IngestionJob.document_version_id == version_id)
    )
    if version.status == DocumentStatus.READY and job is not None and job.progress >= 100:
        return
    # Terminal redeliveries must not change status, attempts or error information.
    document = await session.get(Document, version.document_id)
    if document is None or document.deleted_at is not None or job is None:
        return
    job.attempts += 1
    job.error_code = job.error_message = job.error_details = None
    await _set_stage(session, document, version, job, DocumentStatus.PARSING, 20)
    try:
        await _run_pipeline(session, document, version, job)
    except IngestionError as exc:
        logger.exception("Ingestion failed for version %s (%s)", version_id, exc.code)
        await _record_failure(
            session, version_id, exc, failed=not exc.retryable or retries >= max_retries
        )
        raise
    except Exception as exc:
        logger.exception("Unexpected ingestion failure for version %s", version_id)
        error = IngestionError("INGESTION_FAILED", str(exc), retryable=False)
        await _record_failure(session, version_id, error, failed=True)
        raise error from exc


async def _process_document_version(
    version_id: uuid.UUID, *, retries: int = 0, max_retries: int = 3
) -> None:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            async with try_ingestion_lock(connection, version_id) as acquired:
                if not acquired:
                    logger.info("Ignoring concurrent delivery for version %s", version_id)
                    return
                # The session and lock share a pinned connection. Commits cannot release the lock.
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    await _run_attempt(
                        session, version_id, retries=retries, max_retries=max_retries
                    )
    finally:
        await engine.dispose()


@celery_app.task(bind=True, max_retries=3, name="documents.ingest_version")
def ingest_document_version(self: Task, document_version_id: str) -> None:
    try:
        asyncio.run(
            _process_document_version(
                uuid.UUID(document_version_id),
                retries=self.request.retries,
                max_retries=self.max_retries,
            )
        )
    except IngestionError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=min(60, 2 ** (self.request.retries + 1))) from exc
        raise
