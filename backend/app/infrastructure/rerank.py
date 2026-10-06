import logging
from collections import Counter
from dataclasses import replace

from raghub_core.ports.rerank import RerankRuntime
from sqlalchemy import select

from app.core.config import get_settings
from app.infrastructure.persistence.provider_descriptors import provider_descriptor
from app.modules.ai_providers.models import ProviderConfig
from app.modules.ai_providers.schemas import RerankOptions, validate_connection_endpoint
from app.modules.ai_providers.workspace_ai_router import available
from app.modules.workspaces.models import Workspace

logger = logging.getLogger(__name__)
RERANK_REQUESTS = Counter()


def record_rerank_status(status):
    RERANK_REQUESTS[status] += 1
    logger.info("retrieval_rerank status=%s", status)


class WorkspaceRerankResolver:
    def __init__(self, session, providers):
        self.session, self.providers = session, providers

    async def resolve_rerank(self, scope):
        if not get_settings().ai_rerank_enabled:
            return None
        row = (
            await self.session.execute(
                select(Workspace, ProviderConfig)
                .join(ProviderConfig, ProviderConfig.id == Workspace.rerank_provider_id)
                .where(
                    Workspace.id == scope.workspace_id,
                    Workspace.organization_id == scope.organization_id,
                    Workspace.deleted_at.is_(None),
                    ProviderConfig.organization_id == scope.organization_id,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        workspace, config = row
        available(config, "RERANK")
        validate_connection_endpoint(config.connection)
        options = RerankOptions.model_validate(workspace.rerank_config or {})
        descriptor = provider_descriptor(config)
        descriptor = replace(
            descriptor,
            options={
                **descriptor.options,
                "max_attempts": 1,
                "read_timeout": options.timeout_seconds,
            },
        )
        provider = self.providers.registry.create(descriptor, self.providers._secret(config))
        return RerankRuntime(
            provider, options.candidate_limit, options.top_n, options.timeout_seconds
        )
