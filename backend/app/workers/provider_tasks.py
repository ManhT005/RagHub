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
