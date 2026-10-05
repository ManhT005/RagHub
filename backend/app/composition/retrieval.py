from raghub_core.api import RetrieveContextUseCase
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.elasticsearch.chunks import ChunkSearch
from app.infrastructure.elasticsearch.vector_store import ElasticsearchVectorSearch
from app.infrastructure.persistence.readiness import DocumentReadinessAdapter
from app.infrastructure.providers import ProviderResolverAdapter
from app.infrastructure.rerank import WorkspaceRerankResolver, record_rerank_status
from app.modules.ai_providers.resolver import ProviderResolver


def retrieval_use_case(session: AsyncSession) -> RetrieveContextUseCase:
    providers = ProviderResolver(session)
    return RetrieveContextUseCase(
        ProviderResolverAdapter(providers),
        DocumentReadinessAdapter(session),
        lambda runtime: ElasticsearchVectorSearch(ChunkSearch(index_name=runtime.index_name)),
        WorkspaceRerankResolver(session, providers),
        record_rerank_status,
    )
