"""One-batch embedding worker: each task run embeds a single batch, then requeues."""

import asyncio
import uuid

from celery import Task
from raghub_core.domain.providers.descriptor import ProviderDescriptor
from raghub_core.ports.embedding_quota import QuotaBackendUnavailableError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.redis.quota_buckets import QuotaBucketStore
from app.infrastructure.task_queue.celery_app import celery_app
from app.modules.ai_providers.crypto import ProviderSecretCipher
from app.modules.ai_providers.models import EmbeddingWorkItem
from app.modules.ai_providers.pools import PoolCredential, select_healthy_credential
from app.modules.ai_providers.registry import ProviderRegistry
from app.modules.ai_providers.work_items import (
    WorkItemProcessor,
    WorkItemRepository,
)


async def _process_one_batch(session: AsyncSession, item_id: uuid.UUID) -> bool:
    settings = get_settings()
    repository = WorkItemRepository(session)
    redis = Redis.from_url(settings.redis_url, socket_timeout=2)
    quota = QuotaBucketStore(redis, settings)
    storage = MinioObjectStorage(settings)
    cipher = ProviderSecretCipher(settings.provider_master_key)
    registry = ProviderRegistry()

    async def embed_texts(texts: list[str]) -> list[list[float]]:
        item = await session.get(EmbeddingWorkItem, item_id)
        assert item is not None
        pool = await repository.pool_for(item)
        rows = await repository.credentials_for(pool.id)
        picked = select_healthy_credential(
            [PoolCredential(id=r.id, enabled=r.enabled, unhealthy=r.unhealthy) for r in rows]
        )
        credential = next(r for r in rows if r.id == picked.id)
        secret = (
            cipher.decrypt(credential.encrypted_secret) if credential.encrypted_secret else None
        )
        provider = registry.create(
            ProviderDescriptor(
                provider_type=pool.provider_type,
                capability=pool.capability,
                model=pool.model,
                base_url=None,
                dimension=pool.dimension,
                options=pool.embedding_options or {},
            ),
            secret,
        )
        return await provider.embed_documents(texts)

    async def finalize(item_id: uuid.UUID, vectors: list[list[float]]) -> None:
        import gzip
        import hashlib
        import json

        receipt = json.dumps(
            {
                "work_item_id": str(item_id),
                "batches": len(vectors),
                "dimension": len(vectors[0]) if vectors else 0,
                "sha256": hashlib.sha256(json.dumps(vectors).encode()).hexdigest(),
            }
        ).encode()
        item = await session.get(EmbeddingWorkItem, item_id)
        assert item is not None
        await storage.put(
            f"{item.organization_id}/{item.workspace_id}/embedding-batches/{item_id}/completed.json.gz",
            gzip.compress(receipt),
            "application/gzip",
        )

    processor = WorkItemProcessor(
        repository,
        quota,
        load_blob=storage.get,
        store_blob=lambda key, blob: storage.put(key, blob, "application/gzip"),
        embed_texts=embed_texts,
        finalize=finalize,
    )
    try:
        outcome = await processor.process_one(item_id)
    finally:
        await redis.aclose()
    return outcome.done


@celery_app.task(bind=True, max_retries=None, name="embedding.process_work_item_batch")
def process_work_item_batch(self: Task, work_item_id: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)

    async def run() -> bool:
        async with AsyncSession(engine) as session:
            return await _process_one_batch(session, uuid.UUID(work_item_id))

    try:
        done = asyncio.run(run())
    except QuotaBackendUnavailableError as exc:
        # Fail closed: requeue without touching the provider.
        raise self.retry(exc=exc, countdown=30) from exc
    finally:
        asyncio.run(engine.dispose())
    if not done:
        self.retry(countdown=5)
