from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.elasticsearch.chunks import ChunkSearch
from app.infrastructure.elasticsearch.vector_store import ElasticsearchVectorSearch
from app.infrastructure.persistence.readiness import DocumentReadinessAdapter
from app.infrastructure.providers import ProviderResolverAdapter
from app.modules.ai_providers.resolver import ProviderResolver
from raghub_core.api import RetrieveContextUseCase


def retrieval_use_case(session: AsyncSession) -> RetrieveContextUseCase:
    return RetrieveContextUseCase(
        ProviderResolverAdapter(ProviderResolver(session)),
        DocumentReadinessAdapter(session),
        lambda runtime: ElasticsearchVectorSearch(ChunkSearch(index_name=runtime.index_name)),
    )
