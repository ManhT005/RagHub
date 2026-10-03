"""Worker host wiring for the same ingestion and reindex business pipeline."""

from app.application.ingestion.build_document_index import BuildDocumentIndexUseCase
from app.application.ingestion.reindex_workspace import ReindexWorkspaceUseCase
from app.application.ingestion.run_ingestion import RunIngestionUseCase
from app.core.config import get_settings
from app.core_domain.ingestion.chunker import chunk_sections
from app.infrastructure.elasticsearch.chunks import ChunkIndexer
from app.infrastructure.elasticsearch.vector_store import LegacyVectorStoreAdapter
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.parsing.documents import DocumentParser
from app.infrastructure.persistence.ingestion import IngestionRepositoryAdapter
from app.infrastructure.persistence.reindex import ReindexRepositoryAdapter
from app.infrastructure.providers import ProviderResolverAdapter
from app.modules.ai_providers.resolver import ProviderResolver

parse_document = DocumentParser().parse


class WorkerContainer:
    def __init__(self, session, settings=None):
        self.session = session
        self.settings = settings or get_settings()

    def builder(self):
        return BuildDocumentIndexUseCase(
            MinioObjectStorage(self.settings),
            parse_document,
            chunker=chunk_sections,
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
