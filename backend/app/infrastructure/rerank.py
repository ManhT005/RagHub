import logging
from collections import Counter
from dataclasses import replace

from raghub_core.ports.rerank import RerankRuntime
from sqlalchemy import select

from app.core.config import get_settings
from app.infrastructure.ai.local_reranker import LocalRerankProvider, local_reranker
from app.infrastructure.ai.workspace_reranker import local_installation
from app.infrastructure.persistence.provider_descriptors import provider_descriptor
from app.modules.ai_providers.models import ProviderConfig
from app.modules.ai_providers.schemas import (
    WorkspaceRerankOptions,
    validate_connection_endpoint,
    workspace_rerank_mode,
)
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
        workspace = await self.session.scalar(
            select(Workspace).where(
                Workspace.id == scope.workspace_id,
                Workspace.organization_id == scope.organization_id,
                Workspace.deleted_at.is_(None),
            )
        )
        if workspace is None:
            return None
        settings = get_settings()
        mode = workspace_rerank_mode(
            workspace.rerank_config or {}, workspace.rerank_provider_id, settings
        )
        if mode == "off":
            return None
        options = WorkspaceRerankOptions.model_validate(workspace.rerank_config or {})
        if mode == "local":
            local, paths = await local_installation(self.session, scope.organization_id)
            if not local["ready"] or paths is None:
                raise RuntimeError("Local reranker is not ready")
            # Legacy global deployments keep their original tuning.
            if not workspace.rerank_config:
                options = WorkspaceRerankOptions(
                    candidate_limit=settings.rag_rerank_source_count,
                    top_n=settings.rag_rerank_top_n,
                    timeout_seconds=settings.rag_reranker_timeout_seconds,
                )
            adapter = local_reranker(
                snapshot_path=paths[0],
                expected_sha256=paths[1],
                timeout_seconds=options.timeout_seconds,
            )
            return RerankRuntime(
                LocalRerankProvider(adapter),
                options.candidate_limit,
                options.top_n,
                options.timeout_seconds,
            )
        config = await self.session.scalar(
            select(ProviderConfig).where(
                ProviderConfig.id == workspace.rerank_provider_id,
                ProviderConfig.organization_id == scope.organization_id,
            )
        )
        if config is None:
            raise RuntimeError("Workspace rerank provider is unavailable")
        available(config, "RERANK")
        validate_connection_endpoint(config.connection)
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
