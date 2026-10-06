"""Host-owned execution policy; execution knobs never affect vector identity."""

from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import BaseModel, Field
from raghub_core.domain.ingestion.errors import IngestionError
from sqlalchemy import select

PROFILES = {"conservative": (1, 16, 8000), "balanced": (2, 32, 20000), "fast": (4, 48, 35000)}
EXECUTION_KEYS = frozenset(
    {
        "embedding_speed_profile",
        "max_inflight_requests",
        "max_batch_chunks",
        "max_batch_tokens",
        "retry_max_attempts",
        "retry_delay_seconds",
    }
)
LOCAL_TYPES = {"LOCAL_SENTENCE_TRANSFORMER", "LOCAL_TOKEN_HASH", "OLLAMA"}


def semantic_options(options):
    return {k: v for k, v in (options or {}).items() if k not in EXECUTION_KEYS}


class EmbeddingDeferred(IngestionError):
    def __init__(self):
        super().__init__("EMBEDDING_DEFERRED", "Durable embedding queued.", retryable=False)


class ExecutionPreference(BaseModel):
    profile: Literal["conservative", "balanced", "fast", "custom"] | None = None
    max_inflight_requests: int | None = Field(default=None, ge=1, le=16)
    batch_max_chunks: int | None = Field(default=None, ge=1, le=100)
    batch_target_tokens: int | None = Field(default=None, ge=1000, le=100000)
    retry_max_attempts: int | None = Field(default=None, ge=1, le=48)
    retry_delay_seconds: int | None = Field(default=None, ge=2, le=120)


@dataclass(frozen=True)
class ExecutionPolicy:
    profile: str
    max_inflight_requests: int
    batch_max_chunks: int
    batch_target_tokens: int
    retry_max_attempts: int = 8
    retry_delay_seconds: int = 10
    limited_by: str = "none"
    provider_type: str = "unknown"

    def snapshot(self):
        return asdict(self)


def resolve_policy(settings, provider_type, provider_options=None, workspace_options=None):
    provider = provider_options or {}
    preference = ExecutionPreference.model_validate(workspace_options or {})
    profile = (
        preference.profile
        or provider.get("embedding_speed_profile")
        or (settings.rag_embedding_speed_profile)
    )
    if profile not in {*PROFILES, "custom"}:
        raise ValueError("Unknown embedding speed profile")
    defaults = PROFILES.get(profile, (1, 24, 10000))
    custom = (
        preference.max_inflight_requests or settings.rag_embedding_max_inflight_requests,
        preference.batch_max_chunks or settings.rag_embedding_batch_max_chunks,
        preference.batch_target_tokens or settings.rag_embedding_batch_target_tokens,
    )
    requested = list(defaults)
    if profile == "custom":
        requested = [v or d for v, d in zip(custom, defaults, strict=True)]
    caps = [
        settings.rag_embedding_max_inflight_hard_cap,
        settings.rag_embedding_max_batch_chunks_hard_cap,
        settings.rag_embedding_max_batch_tokens_hard_cap,
    ]
    effective = [min(v, cap) for v, cap in zip(requested, caps, strict=True)]
    limited = "host" if effective != requested else "none"
    provider_caps = PROFILES.get(provider.get("embedding_speed_profile"), caps)
    for i, key in enumerate(("max_inflight_requests", "max_batch_chunks", "max_batch_tokens")):
        cap = min(provider_caps[i], int(provider.get(key) or caps[i]))
        if cap < 1:
            raise ValueError("Provider execution caps must be positive")
        if cap < effective[i]:
            effective[i], limited = cap, "provider"
    if provider_type in LOCAL_TYPES or provider_type == "unknown":
        local_chunks = {"lite_cpu": 16, "standard_cpu": 24, "gpu": 48}.get(
            settings.rag_hardware_profile, 24
        )
        local = [1, local_chunks, 10000]
        if any(v > cap for v, cap in zip(effective, local, strict=True)):
            limited = "local"
        effective = [min(v, cap) for v, cap in zip(effective, local, strict=True)]
    return ExecutionPolicy(
        profile,
        *effective,
        min(
            48,
            max(1, preference.retry_max_attempts or int(provider.get("retry_max_attempts") or 8)),
        ),
        min(
            120,
            max(
                2, preference.retry_delay_seconds or int(provider.get("retry_delay_seconds") or 10)
            ),
        ),
        limited,
        str(provider_type),
    )


class ExecutionRuntimeResponse(BaseModel):
    profile: str
    preference: ExecutionPreference
    effective_max_inflight: int
    effective_batch_chunks: int
    effective_batch_tokens: int
    limited_by: str
    local: bool
    max_allowed_inflight: int
    max_allowed_batch_chunks: int
    max_allowed_batch_tokens: int


async def policy_for_workspace(
    session, settings, workspace_id, *, index_name=None, preference_override=None
):
    from app.modules.ai_providers.models import EmbeddingIndexVersion, ProviderConfig
    from app.modules.workspaces.models import Workspace

    workspace = await session.get(Workspace, workspace_id)
    if index_name:
        version = await session.scalar(
            select(EmbeddingIndexVersion).where(
                EmbeddingIndexVersion.index_name == index_name,
                EmbeddingIndexVersion.workspace_id == workspace_id,
            )
        )
    elif workspace is not None and workspace.active_embedding_index_version_id:
        version = await session.get(
            EmbeddingIndexVersion, workspace.active_embedding_index_version_id
        )
    else:
        version = None
    if version is None:
        return resolve_policy(
            settings,
            "unknown",
            workspace_options=preference_override
            if preference_override is not None
            else getattr(workspace, "embedding_execution_config", None),
        )
    config = await session.get(ProviderConfig, version.provider_config_id)
    options = {}
    if config is not None:
        connection_options = {}
        if getattr(config, "connection", None):
            connection_options = config.connection.config_json or {}
            options.update(connection_options)
        options.update(config.config_json or {})
        # A model profile cannot lift its connection's execution ceiling.
        connection_profile = PROFILES.get(connection_options.get("embedding_speed_profile"))
        for i, key in enumerate(("max_inflight_requests", "max_batch_chunks", "max_batch_tokens")):
            cap = connection_options.get(key)
            if connection_profile:
                cap = min(int(cap or connection_profile[i]), connection_profile[i])
            if cap is not None:
                options[key] = min(int(cap), int(options.get(key) or cap))
    return resolve_policy(
        settings,
        str(version.provider_type),
        options,
        preference_override
        if preference_override is not None
        else getattr(workspace, "embedding_execution_config", None),
    )


def configure_batch_provider(provider):
    """Let the durable worker own retries; avoid sleeping inside an API adapter."""
    from dataclasses import replace

    for adapter in getattr(provider, "providers", [provider]):
        if hasattr(adapter, "policy"):
            adapter.policy = replace(adapter.policy, max_attempts=1)
