"""Managed provider pools: backfill mapping and compatible-only failover.

Workspace code binds to a pool (profile); credentials stay platform-managed
and are never exposed through the provider CRUD facade.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from raghub_core.domain.providers.fingerprint import embedding_fingerprint_v2, quota_scope


@dataclass(frozen=True)
class LegacyProviderRow:
    id: UUID
    organization_id: UUID
    provider_type: str
    capability: str
    base_url: str | None
    model: str
    dimension: int | None
    encrypted_secret: str | None
    config_json: dict


@dataclass(frozen=True)
class BackfilledPool:
    pool_id: UUID
    organization_id: UUID
    provider_type: str
    capability: str
    model: str
    dimension: int | None
    fingerprint_v2: str
    quota_scope: str
    primary_encrypted_secret: str | None


def backfill_pool_for_config(row: LegacyProviderRow, *, pool_id: UUID) -> BackfilledPool:
    """Map one legacy ProviderConfig to one pool + primary credential.

    The ciphertext is copied verbatim: never decrypt/re-encrypt during backfill.
    """
    options = row.config_json or {}
    task_type = options.get("task_type")
    project = options.get("quota_project") or options.get("project_id")
    return BackfilledPool(
        pool_id=pool_id,
        organization_id=row.organization_id,
        provider_type=row.provider_type,
        capability=row.capability,
        model=row.model,
        dimension=row.dimension,
        fingerprint_v2=embedding_fingerprint_v2(
            provider_type=row.provider_type,
            base_url=row.base_url,
            model=row.model,
            dimension=row.dimension,
            task_type=task_type,
            embedding_options=options,
        ),
        quota_scope=quota_scope(
            provider_type=row.provider_type, model=row.model, project=project
        ),
        primary_encrypted_secret=row.encrypted_secret,
    )


@dataclass(frozen=True)
class PoolCredential:
    id: UUID
    enabled: bool
    unhealthy: bool


class PoolExhaustedError(Exception):
    pass


class FingerprintMismatchError(Exception):
    pass


def select_healthy_credential(
    credentials: list[PoolCredential], *, exclude_ids: set[UUID] | None = None
) -> PoolCredential:
    """Pick the first healthy credential in the same pool/fingerprint.

    Only credentials of the resolved pool are candidates, so cross-model
    fallback is impossible by construction.
    """
    excluded = exclude_ids or set()
    for credential in credentials:
        if credential.enabled and not credential.unhealthy and credential.id not in excluded:
            return credential
    raise PoolExhaustedError("No healthy credential left in the pool.")


def resolve_pool_for_fingerprint(
    pools: dict[str, UUID], fingerprint: str
) -> UUID:
    """Resolve the pool serving the active index fingerprint, or fail closed."""
    try:
        return pools[fingerprint]
    except KeyError as exc:
        raise FingerprintMismatchError(
            "No managed pool matches the active index fingerprint."
        ) from exc


def classify_provider_failure(status_code: int | None) -> str:
    """Map an HTTP failure to pool handling: unhealthy vs quota wait."""
    if status_code in (401, 403):
        return "unhealthy"
    if status_code == 429:
        return "quota"
    return "retryable"
