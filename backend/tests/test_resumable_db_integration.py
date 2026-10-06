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


async def test_pool_credentials_follow_connection_rotation_and_persist_auth_health(
    isolated_sessions,
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from raghub_core.domain.providers.errors import ProviderAuthenticationError

    from app.modules.ai_providers.crypto import ProviderSecretCipher
    from app.modules.ai_providers.models import ProviderConnection, ProviderCredential
    from app.modules.ai_providers.resolver import ProviderResolver
    from app.modules.ai_providers.service import ProviderConfigService, config_fingerprint_v2

    async with isolated_sessions(expire_on_commit=False) as session:
        org, _, index, _ = await seed(session)
        cipher = ProviderSecretCipher("raghub-ci-provider-key-not-for-production")
        models = []
        for key in ["bad-key", "good-key"]:
            connection = ProviderConnection(
                organization_id=org.id,
                name=key,
                provider_type="OPENAI_COMPATIBLE",
                catalog_id="openai",
                base_url="https://api.openai.com/v1",
                encrypted_secret=cipher.encrypt(key),
                config_json={},
                enabled=True,
            )
            config = ProviderConfig(
                organization_id=org.id,
                name=key,
                connection=connection,
                provider_type="OPENAI_COMPATIBLE",
                capability="EMBEDDING",
                base_url=connection.base_url,
                model="text-embedding-3-small",
                dimension=384,
                config_json={},
                enabled=True,
            )
            session.add(config)
            await session.flush()
            models.append(config)
        service = ProviderConfigService(session)
        first_pool = await service._ensure_pool(models[0])
        assert (await service._ensure_pool(models[1])).id == first_pool.id
        first_credential = await session.scalar(
            select(ProviderCredential).where(ProviderCredential.provider_config_id == models[0].id)
        )
        assert first_credential.encrypted_secret is None
        first_id = first_credential.id
        index.provider_config_id = models[0].id
        index.provider_type, index.base_url = models[0].provider_type, models[0].base_url
        index.model, index.config_json = models[0].model, {}
        index.embedding_fingerprint_v2 = config_fingerprint_v2(models[0])
        second_id, index_id = models[1].id, index.id
        await session.commit()
        resolved_keys = []

        def create(descriptor, key):
            resolved_keys.append(key)
            return SimpleNamespace(
                metadata=None,
                embed_query=AsyncMock(
                    side_effect=ProviderAuthenticationError() if key == "bad-key" else None,
                    return_value=[1.0] * 384,
                ),
            )

        resolver = ProviderResolver(session, registry=SimpleNamespace(create=create), cipher=cipher)
        runtime = await resolver.embedding_for_version(index)
        assert len(await runtime.provider.embed_query("query")) == 384
        await session.rollback()  # Search rollback must not resurrect the bad credential.
        async with isolated_sessions() as check:
            assert (await check.get(ProviderCredential, first_id)).unhealthy
        second = await session.get(ProviderConfig, second_id)
        second.connection.encrypted_secret = cipher.encrypt("rotated-key")
        await session.commit()
        index = await session.get(EmbeddingIndexVersion, index_id)
        resolved_keys.clear()
        await resolver.embedding_for_version(index)
        assert resolved_keys == ["rotated-key"]


async def seed(session, managed_pool=False, document_pipeline="legacy"):
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
        config_json={}
        if document_pipeline == "legacy"
        else {"document_pipeline": document_pipeline},
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
        config_json=provider.config_json,
    )
    session.add(index)
    await session.flush()
    if managed_pool:
        from app.modules.ai_providers.models import ProviderCredential, ProviderPool
        from app.modules.ai_providers.service import config_fingerprint_v2

        index.embedding_fingerprint_v2 = config_fingerprint_v2(provider)
        pool = ProviderPool(
            organization_id=org.id,
            provider_type=provider.provider_type,
            capability="EMBEDDING",
            model=provider.model,
            dimension=384,
            embedding_options=provider.config_json,
            quota_scope="local",
            fingerprint_v2=index.embedding_fingerprint_v2,
        )
        session.add(pool)
        await session.flush()
        session.add(ProviderCredential(pool_id=pool.id, name="primary", enabled=True))
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


async def test_reindex_reserves_upload_admission_and_yields_claim_priority(isolated_sessions):
    async with isolated_sessions(expire_on_commit=False) as session:
        org, ws, _, version = await seed(session)
        repo = WorkItemRepository(session, Settings(provider_pool_max_pending_jobs_per_workspace=2))
        kwargs = dict(
            organization_id=org.id, workspace_id=ws.id, pool_id=None, document_version_id=version.id
        )
        background = await repo.create(**kwargs, kind="reindex")
        with pytest.raises(ValueError, match="queue is full"):
            await repo.create(**kwargs, kind="reindex")
        upload = await repo.create(**kwargs, kind="upload")
        await session.commit()
        assert await repo.claim(background.id) is None
        assert await repo.claim(upload.id) is not None
        await repo.complete(upload)
        assert await repo.claim(background.id) is not None
        await session.rollback()


@pytest.mark.parametrize(
    "managed_pool,document_pipeline",
    [(False, "legacy"), (True, "legacy"), (True, "normalized-v1"), (True, "context-v1")],
)
async def test_canonical_upload_publishes_real_index_after_durable_batches(
    isolated_sessions, managed_pool, document_pipeline
):
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
        org, ws, index, version = await seed(session, managed_pool, document_pipeline)
        storage = MinioObjectStorage(settings)
        await storage.put(
            version.storage_key, b"A useful  guide to configuration. " * 1000, "text/plain"
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
                source = indexer.client.search(index=index.index_name, size=1)["hits"]["hits"][0][
                    "_source"
                ]
                assert "useful  guide" in source["raw_content"]
                if document_pipeline != "legacy":
                    assert "useful  guide" not in source["content"]
                    assert source["parent_section_id"]
                if document_pipeline == "normalized-v1":
                    from raghub_core.domain.retrieval.models import RetrievalScope

                    from scripts.run_retrieval_ablation import collect

                    hits = indexer.client.search(index=index.index_name, size=250)["hits"]["hits"]
                    expected = [h["_source"]["chunk_id"] for h in hits]
                    cases = [
                        {
                            "id": "a",
                            "question": "useful guide",
                            "answerable": True,
                            "split": "calibration",
                        }
                    ]
                    configs = [
                        {"candidates": 15, "rrf_k": 60, "max_per_document": cap} for cap in (1, 2)
                    ]
                    report = await collect(
                        session,
                        settings,
                        RetrievalScope(org.id, ws.id),
                        cases,
                        configs,
                        {"a": expected},
                    )
                    assert report["document_pipeline"] == document_pipeline
                    for cap, cell in zip((1, 2), report["results"], strict=False):
                        assert cell["cases"][0]["hit@5"] == 1
                        assert len(cell["cases"][0]["ranked_chunk_ids"]) == cap
                        assert cell["summary"]["search_p95_ms"] > 0
            finally:
                indexer.client.indices.delete(index=index.index_name)
                indexer.close()
        finally:
            await storage.remove(version.storage_key)
