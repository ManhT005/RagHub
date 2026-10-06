import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.infrastructure.task_queue.celery_app import celery_app
from app.modules.installation.local_ai_bootstrap import LocalAiBootstrapService


async def bootstrap_health(organization_id, model_ids):
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await LocalAiBootstrapService(session).health_check(
                UUID(organization_id), [UUID(value) for value in model_ids]
            )
    finally:
        await engine.dispose()


@celery_app.task(name="providers.bootstrap_health", soft_time_limit=280, time_limit=300)
def run_bootstrap_health(organization_id, model_ids):
    asyncio.run(bootstrap_health(organization_id, model_ids))


async def ollama_pull(job_id):
    from app.modules.ai_providers.ollama_manager import OllamaModelManager

    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await OllamaModelManager(session).run(UUID(job_id))
    finally:
        await engine.dispose()


@celery_app.task(
    name="providers.ollama_pull",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=7100,
    time_limit=7200,
)
def run_ollama_pull(job_id):
    asyncio.run(ollama_pull(job_id))


async def local_download(job_id):
    from app.modules.ai_providers.local_manager import LocalModelManager

    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await LocalModelManager(session).run(UUID(job_id))
    finally:
        await engine.dispose()


@celery_app.task(name="providers.local_download", soft_time_limit=3500, time_limit=3600)
def run_local_download(job_id):
    asyncio.run(local_download(job_id))
