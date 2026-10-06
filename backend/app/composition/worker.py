"""Worker host wiring for the same ingestion and reindex business pipeline."""

from raghub_core.api import (
    BuildDocumentIndexUseCase,
    ReindexWorkspaceUseCase,
    RunIngestionUseCase,
)
from raghub_core.domain.ingestion.chunker import chunk_sections
from raghub_core.ports.embedding_quota import EmbeddingQuotaPort

from app.core.config import get_settings
from app.infrastructure.elasticsearch.chunks import ChunkIndexer
from app.infrastructure.elasticsearch.vector_store import LegacyVectorStoreAdapter
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.parsing.documents import DocumentParser
from app.infrastructure.persistence.index_metadata import MetadataIndexBuilder
from app.infrastructure.persistence.ingestion import IngestionRepositoryAdapter
from app.infrastructure.persistence.reindex import ReindexRepositoryAdapter
from app.infrastructure.providers import ProviderResolverAdapter
from app.infrastructure.resumable_embedding import ResumableEmbedding
from app.modules.ai_providers.resolver import ProviderResolver

parse_document = DocumentParser().parse


class WorkerContainer:
    def __init__(self, session, settings=None, *, quota: EmbeddingQuotaPort | None = None):
        self.session = session
        self.settings = settings or get_settings()
        self.quota = quota

    def builder(self):
        storage = MinioObjectStorage(self.settings)
        embeddings = ResumableEmbedding(self.session, storage, self.settings, self.quota)
        return MetadataIndexBuilder(
            BuildDocumentIndexUseCase(
                storage,
                parse_document,
                chunker=chunk_sections,
                quota=self.quota,
                embedding_executor=embeddings.execute,
            ),
            self.session,
            embeddings=embeddings,
        )

    def make_store(self, runtime):
        return LegacyVectorStoreAdapter(
            ChunkIndexer(
                settings=self.settings,
                index_name=runtime.index_name,
                dimension=runtime.dimension,
            )
        )

    def providers(self):
        return ProviderResolverAdapter(ProviderResolver(self.session))

    def ingestion_repository(self, **kwargs):
        return IngestionRepositoryAdapter(self.session, **kwargs)

    def run_ingestion(self, repository=None, *, pipeline=None):
        return RunIngestionUseCase(
            repository or self.ingestion_repository(),
            self.builder(),
            self.providers(),
            self.make_store,
            pipeline=pipeline,
        )

    def reindex_workspace(self):
        return ReindexWorkspaceUseCase(
            ReindexRepositoryAdapter(self.session),
            self.builder(),
            self.providers(),
            self.make_store,
        )
