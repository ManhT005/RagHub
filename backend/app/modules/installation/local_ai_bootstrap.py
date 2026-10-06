"""Local defaults use the same connection/model lifecycle as the provider registry."""

import asyncio
import logging
from datetime import UTC, datetime

from raghub_core.domain.errors import CoreError
from sqlalchemy import select

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.modules.ai_providers.catalog import supported_catalog_by_id
from app.modules.ai_providers.control_service import health_error
from app.modules.ai_providers.models import ProviderConfig, ProviderConnection
from app.modules.ai_providers.service import ProviderConfigService
from app.modules.organizations.models import OrganizationAiDefaults

logger = logging.getLogger(__name__)


class LocalAiBootstrapService:
    def __init__(self, session):
        self.session = session

    async def ensure(self, organization_id):
        models = []
        for catalog_id, name, provider_type, model, capability, dimension, base_url in (
            (
                "sentence-transformer",
                "Local Embedding",
                "LOCAL_SENTENCE_TRANSFORMER",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                "EMBEDDING",
                384,
                None,
            ),
            (
                "ollama",
                "Local Chat",
                "OLLAMA",
                "gemma3:1b",
                "CHAT",
                None,
                get_settings().ollama_base_url,
            ),
        ):
            catalog = supported_catalog_by_id(catalog_id)
            options = {
                "endpoint_scope": catalog.endpoint_scope,
                "request_profile": catalog.request_profile,
            }
            connection = await self.session.scalar(
                select(ProviderConnection)
                .where(
                    ProviderConnection.organization_id == organization_id,
                    ProviderConnection.catalog_id == catalog_id,
                    ProviderConnection.base_url == base_url,
                )
                .order_by(ProviderConnection.created_at)
                .limit(1)
            )
            if connection is None:
                connection = ProviderConnection(
                    organization_id=organization_id,
                    catalog_id=catalog_id,
                    name=name,
                    provider_type=provider_type,
                    base_url=base_url,
                    enabled=True,
                    config_json=options,
                    status="UNTESTED",
                )
                self.session.add(connection)
                await self.session.flush()
            config = await self.session.scalar(
                select(ProviderConfig).where(
                    ProviderConfig.connection_id == connection.id,
                    ProviderConfig.model == model,
                    ProviderConfig.capability == capability,
                )
            )
            if config is None:
                config = ProviderConfig(
                    organization_id=organization_id,
                    connection=connection,
                    name=model,
                    display_name=model,
                    provider_type=provider_type,
                    model=model,
                    capability=capability,
                    dimension=dimension,
                    base_url=base_url,
                    config_json=options,
                    enabled=True,
                    availability_status="UNTESTED",
                )
                self.session.add(config)
                await self.session.flush()
            models.append(config)
        defaults = await self.session.get(OrganizationAiDefaults, organization_id)
        if defaults is None:
            defaults = OrganizationAiDefaults(organization_id=organization_id)
            self.session.add(defaults)
        defaults.default_embedding_model_id, defaults.default_chat_model_id = (
            config.id for config in models
        )
        await self.session.flush()
        return models

    async def health_check(self, organization_id, model_ids):
        from app.modules.ai_providers.local_models import LocalModelDownload
        from app.modules.ai_providers.models import OllamaModelPull

        for model_id in model_ids:
            service = ProviderConfigService(self.session)
            config = await service.get(organization_id, model_id)
            if hasattr(self.session, "scalar"):
                if getattr(config, "provider_type", None) == "OLLAMA":
                    active_pull = await self.session.scalar(
                        select(OllamaModelPull).where(
                            OllamaModelPull.connection_id == config.connection_id,
                            OllamaModelPull.status.in_(("QUEUED", "PULLING", "VERIFYING")),
                        )
                    )
                    if active_pull:
                        logger.info(
                            "Skipping health probe for Ollama model %s while pull is in progress",
                            config.model,
                        )
                        continue
                elif getattr(config, "provider_type", None) == "LOCAL_SENTENCE_TRANSFORMER":
                    active_dl = await self.session.scalar(
                        select(LocalModelDownload).where(
                            LocalModelDownload.organization_id == organization_id,
                            LocalModelDownload.status.in_(("QUEUED", "DOWNLOADING", "VERIFYING")),
                        )
                    )
                    if active_dl:
                        logger.info(
                            "Skipping health probe for local model %s while download is in progress",
                            config.model,
                        )
                        continue

            try:
                # Fail-fast timeout: 20 seconds max per provider probe instead of 120s
                async with asyncio.timeout(20):
                    await service.test(organization_id, model_id)
            except (AppError, CoreError, TimeoutError, Exception) as exc:
                config.availability_status = "UNAVAILABLE"
                config.last_health_check_at = datetime.now(UTC)
                if hasattr(config, "connection") and config.connection:
                    config.connection.status = "DEGRADED"
                    config.connection.last_error_code = (
                        health_error(exc) if isinstance(exc, CoreError) else "PROVIDER_UNREACHABLE"
                    )
                await self.session.commit()


def enqueue_local_ai_health(organization_id, model_ids):
    from app.infrastructure.task_queue.celery_app import celery_app

    try:
        celery_app.send_task(
            "providers.bootstrap_health", args=[organization_id, model_ids], retry=False
        )
    except Exception:
        # Owner/session are already committed. Model tests remain available to the admin.
        logger.warning("Local AI health job could not be queued; models remain untested.")
