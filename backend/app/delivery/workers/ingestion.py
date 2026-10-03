import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.application.ingestion.build_document_index import BuildDocumentIndexUseCase
from app.application.ingestion.run_ingestion import RunIngestionUseCase
from app.core.config import get_settings
from app.core_domain.ingestion.chunker import chunk_sections
from app.infrastructure.elasticsearch.chunks import ChunkIndexer
from app.infrastructure.elasticsearch.vector_store import LegacyVectorStoreAdapter
from app.infrastructure.ingestion_lock import try_ingestion_lock
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.persistence.ingestion import (
    IngestionRepositoryAdapter,
)
from app.infrastructure.persistence.ingestion import (
    _record_failure as _record_failure,
)
from app.infrastructure.persistence.ingestion import (
    _set_stage as _set_stage,
)
from app.infrastructure.providers import ProviderResolverAdapter
from app.modules.ai_providers.resolver import ProviderResolver
from app.modules.documents.models import Document, DocumentVersion, IngestionJob
from app.modules.ingestion.parser import (
    parse_document,
)
from app.ports.provider_resolver import EmbeddingRuntime

logger = logging.getLogger(__name__)


async def _run_pipeline(
    session: AsyncSession, document: Document, version: DocumentVersion, job: IngestionJob
) -> None:
    repository = IngestionRepositoryAdapter(session, document=document, version=version, job=job)
    await _make_use_case(session, repository).build(repository.snapshot())


def _make_use_case(
    session: AsyncSession, repository: IngestionRepositoryAdapter, *, pipeline=None
) -> RunIngestionUseCase:
    settings = get_settings()
    builder = BuildDocumentIndexUseCase(
        MinioObjectStorage(settings), parse_document, chunker=chunk_sections
    )

    def make_store(runtime: EmbeddingRuntime):
        indexer = ChunkIndexer(
            settings=settings, index_name=runtime.index_name, dimension=runtime.dimension
        )
        return LegacyVectorStoreAdapter(indexer)

    return RunIngestionUseCase(
        repository,
        builder,
        ProviderResolverAdapter(ProviderResolver(session)),
        make_store,
        pipeline=pipeline,
    )


async def _run_attempt(
    session: AsyncSession, version_id: uuid.UUID, *, retries: int, max_retries: int
) -> None:
    repository = IngestionRepositoryAdapter(session, failure=_record_failure)

    async def pipeline(_document):
        await _run_pipeline(session, repository.document, repository.version, repository.job)

    await _make_use_case(session, repository, pipeline=pipeline).execute(
        version_id, retries=retries, max_retries=max_retries
    )


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
