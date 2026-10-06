from uuid import uuid4

import pytest
from sqlalchemy import select

from app.composition.worker import WorkerContainer
from app.core.config import Settings
from app.modules.ai_providers.models import EmbeddingIndexVersion, EmbeddingWorkItem, ProviderConfig
from app.modules.ai_providers.work_items import WorkItemRepository
from app.modules.documents.models import Document, DocumentVersion, IngestionJob
from app.modules.organizations.models import Organization
from app.modules.workspaces.models import Workspace

pytestmark = pytest.mark.integration


async def seed(session):
    org = Organization(name="Integration", slug=uuid4().hex)
    session.add(org)
    await session.flush()
    ws = Workspace(organization_id=org.id, name="Documents", slug="docs")
    session.add(ws)
    await session.flush()
    provider = ProviderConfig(
        organization_id=org.id,
        name="Local",
        provider_type="LOCAL_TOKEN_HASH",
        capability="EMBEDDING",
        model="token-hash-v1",
        dimension=384,
    )
    session.add(provider)
    await session.flush()
    index = EmbeddingIndexVersion(
        organization_id=org.id,
        workspace_id=ws.id,
        provider_config_id=provider.id,
        provider_type=provider.provider_type,
        model=provider.model,
        dimension=384,
        embedding_fingerprint="local-fp",
        index_name="test-rag-" + uuid4().hex,
        status="ACTIVE",
    )
    session.add(index)
    await session.flush()
    ws.active_embedding_index_version_id = index.id
    doc = Document(organization_id=org.id, workspace_id=ws.id, name="guide.txt", status="QUEUED")
    session.add(doc)
    await session.flush()
    version = DocumentVersion(
        document_id=doc.id,
        organization_id=org.id,
        workspace_id=ws.id,
        storage_key=f"{org.id}/guide.txt",
        checksum="checksum",
        mime_type="text/plain",
        size_bytes=100,
        status="QUEUED",
    )
    session.add(version)
    await session.flush()
    session.add(IngestionJob(document_version_id=version.id, stage="QUEUED", progress=0))
    await session.commit()
    return org, ws, index, version


async def test_real_database_claim_is_exclusive_and_recovers_after_rollback(isolated_sessions):
    async with isolated_sessions(expire_on_commit=False) as first:
        org, ws, _, version = await seed(first)
        repo = WorkItemRepository(first)
        item = await repo.create(
            organization_id=org.id, workspace_id=ws.id, pool_id=None, document_version_id=version.id
        )
        await first.commit()
        item_id = item.id
        assert await repo.claim(item_id) is not None
        async with isolated_sessions() as second:
            assert await WorkItemRepository(second).claim(item_id) is None
            await second.rollback()
        await first.rollback()
        async with isolated_sessions() as third:
            assert await WorkItemRepository(third).claim(item_id) is not None
            await third.rollback()


async def test_canonical_upload_publishes_real_index_after_durable_batches(isolated_sessions):
    import os

    from app.infrastructure.elasticsearch.chunks import ChunkIndexer
    from app.infrastructure.object_storage.minio import MinioObjectStorage

    if not os.getenv("RAGHUB_TEST_ELASTICSEARCH_URL") or not os.getenv("RAGHUB_TEST_S3_ENDPOINT"):
        pytest.skip("Set disposable Elasticsearch and object storage test endpoints.")
    settings = Settings(
        elasticsearch_url=os.environ["RAGHUB_TEST_ELASTICSEARCH_URL"],
        s3_endpoint=os.environ["RAGHUB_TEST_S3_ENDPOINT"],
        s3_access_key="raghub",
        s3_secret_key="raghub-local-only",
        rag_embedding_batch_max_chunks=2,
    )
    async with isolated_sessions(expire_on_commit=False) as session:
        _, _, index, version = await seed(session)
        storage = MinioObjectStorage(settings)
        await storage.put(
            version.storage_key, b"A useful guide to configuration. " * 1000, "text/plain"
        )
        try:
            result = await WorkerContainer(session, settings).run_ingestion().execute(version.id)
            assert result.status == "READY"
            await session.refresh(version)
            assert version.status == "READY" and version.chunk_count > 2
            item = await session.scalar(
                select(EmbeddingWorkItem).where(EmbeddingWorkItem.document_version_id == version.id)
            )
            assert item.state == "COMPLETED"
            assert item.embedded_chunks == item.total_chunks == version.chunk_count
            indexer = ChunkIndexer(index_name=index.index_name, dimension=384, settings=settings)
            try:
                assert (
                    indexer.client.count(
                        index=index.index_name, query={"term": {"retrievable": True}}
                    )["count"]
                    == version.chunk_count
                )
            finally:
                indexer.client.indices.delete(index=index.index_name)
                indexer.close()
        finally:
            await storage.remove(version.storage_key)
