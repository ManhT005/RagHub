import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.infrastructure.elasticsearch.chunks import ChunkIndexer
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.task_queue.celery_app import celery_app
from app.modules.ai_providers.enums import IndexVersionStatus, ReindexJobStatus
from app.modules.ai_providers.models import EmbeddingIndexVersion, EmbeddingReindexJob
from app.modules.ai_providers.resolver import ProviderResolver
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.ingestion.chunker import chunk_sections
from app.modules.ingestion.parser import parse_document
from app.modules.workspaces.models import Workspace

logger = logging.getLogger(__name__)


def _is_current_target(workspace: Workspace, version: EmbeddingIndexVersion) -> bool:
    return workspace.pending_embedding_index_version_id == version.id


def _has_all_document_versions(
    expected: set[uuid.UUID], indexed: set[uuid.UUID]
) -> bool:
    return expected.issubset(indexed)


async def _fail(session: AsyncSession, job_id: uuid.UUID, exc: Exception) -> None:
    await session.rollback()
    job = await session.get(EmbeddingReindexJob, job_id)
    if job is None:
        return
    version = await session.get(EmbeddingIndexVersion, job.target_index_version_id)
    job.status = ReindexJobStatus.FAILED
    remaining = max(1, job.total_documents - job.processed_documents)
    job.failed_documents = max(job.failed_documents, remaining)
    job.error_code = "EMBEDDING_REINDEX_FAILED"
    job.error_message = "The embedding index could not be rebuilt."
    job.completed_at = datetime.now(UTC)
    if version:
        version.status = IndexVersionStatus.FAILED
    await session.commit()
    logger.exception("Embedding re-index job %s failed", job_id, exc_info=exc)


async def _run_reindex(job_id: uuid.UUID) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            job = await session.get(EmbeddingReindexJob, job_id)
            if job is None or job.status not in {
                ReindexJobStatus.QUEUED,
                ReindexJobStatus.RUNNING,
            }:
                return
            version = await session.get(EmbeddingIndexVersion, job.target_index_version_id)
            workspace = await session.get(Workspace, job.workspace_id)
            if version is None or workspace is None:
                return
            if not _is_current_target(workspace, version):
                job.status = ReindexJobStatus.SUPERSEDED
                job.completed_at = datetime.now(UTC)
                await session.commit()
                return
            job.status = ReindexJobStatus.RUNNING
            job.started_at = job.started_at or datetime.now(UTC)
            await session.commit()
            try:
                resolved = await ProviderResolver(session).embedding_for_version(version)
                rows = list(
                    (
                        await session.execute(
                            select(Document, DocumentVersion)
                            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
                            .where(
                                Document.organization_id == job.organization_id,
                                Document.workspace_id == job.workspace_id,
                                Document.status == DocumentStatus.READY,
                                Document.deleted_at.is_(None),
                                DocumentVersion.status == DocumentStatus.READY,
                            )
                            .order_by(DocumentVersion.created_at.desc())
                        )
                    ).all()
                )
                latest_rows: list[tuple[Document, DocumentVersion]] = []
                seen_documents: set[uuid.UUID] = set()
                for document, document_version in rows:
                    if document.id not in seen_documents:
                        latest_rows.append((document, document_version))
                        seen_documents.add(document.id)
                job.total_documents = len(latest_rows)
                await session.commit()
                indexer = ChunkIndexer(
                    settings=settings,
                    index_name=version.index_name,
                    dimension=version.dimension,
                )
                storage = MinioObjectStorage(settings)
                try:
                    indexer.ensure_index()
                    for document, document_version in latest_rows:
                        sections = parse_document(
                            storage.get(document_version.storage_key), document.name
                        )
                        chunks = chunk_sections(sections, document_version.id)
                        vectors = await resolved.provider.embed_documents(
                            [chunk.content for chunk in chunks]
                        )
                        embeddings = {
                            str(chunk.chunk_id): vector
                            for chunk, vector in zip(chunks, vectors, strict=True)
                        }
                        indexer.replace_document_version(
                            organization_id=job.organization_id,
                            workspace_id=job.workspace_id,
                            document_id=document.id,
                            document_version_id=document_version.id,
                            source_name=document.name,
                            chunks=chunks,
                            embeddings=embeddings,
                        )
                        job.processed_documents += 1
                        await session.commit()
                    job.status = ReindexJobStatus.VALIDATING
                    await session.commit()
                    expected_versions = {
                        document_version.id for _, document_version in latest_rows
                    }
                    indexed_versions = indexer.document_version_ids(job.workspace_id)
                    if not _has_all_document_versions(expected_versions, indexed_versions):
                        raise RuntimeError("Re-index validation found missing documents")
                finally:
                    indexer.close()
                job.status = ReindexJobStatus.SWITCHING
                await session.commit()
                await session.refresh(workspace)
                if not _is_current_target(workspace, version):
                    job.status = ReindexJobStatus.SUPERSEDED
                    job.completed_at = datetime.now(UTC)
                    version.status = IndexVersionStatus.FAILED
                    await session.commit()
                    return
                old = await session.get(
                    EmbeddingIndexVersion, workspace.active_embedding_index_version_id
                ) if workspace.active_embedding_index_version_id else None
                if old and old.id != version.id:
                    old.status = IndexVersionStatus.RETIRED
                version.status = IndexVersionStatus.ACTIVE
                version.activated_at = datetime.now(UTC)
                workspace.active_embedding_index_version_id = version.id
                workspace.embedding_provider_id = version.provider_config_id
                workspace.pending_embedding_index_version_id = None
                job.status = ReindexJobStatus.COMPLETED
                job.completed_at = datetime.now(UTC)
                await session.commit()
            except Exception as exc:
                await _fail(session, job_id, exc)
                raise
    finally:
        await engine.dispose()


@celery_app.task(name="providers.reindex_workspace")
def reindex_workspace(job_id: str) -> None:
    asyncio.run(_run_reindex(uuid.UUID(job_id)))
