"""Real GC inventory over Elasticsearch and Postgres (CLI wiring)."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from elasticsearch import Elasticsearch
from raghub_core.domain.providers.enums import ReindexJobStatus
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.elasticsearch.gc import INDEX_PREFIX, IndexCandidate
from app.infrastructure.elasticsearch.gc_runner import GC_LOCK_KEY, GC_LOCK_TTL_SECONDS
from app.modules.ai_providers.gc_models import IndexGcItem, IndexGcRun
from app.modules.ai_providers.models import (
    EmbeddingIndexVersion,
    EmbeddingReindexJob,
    EmbeddingWorkItem,
)
from app.modules.workspaces.models import Workspace


def _age_hours(since) -> float | None:
    if since is None:
        return None
    moment = since if since.tzinfo else since.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - moment).total_seconds() / 3600)


async def load_candidates(session: AsyncSession, es: Elasticsearch) -> list[IndexCandidate]:
    try:
        names = list(es.indices.get(index=f"{INDEX_PREFIX}*"))
    except Exception:
        names = []
    versions = (await session.scalars(select(EmbeddingIndexVersion))).all()
    by_index = {v.index_name: v for v in versions}
    workspaces = {w.id: w for w in (await session.scalars(select(Workspace))).all()}
    busy_versions = set(
        (await session.scalars(
            select(EmbeddingReindexJob.target_index_version_id).where(
                EmbeddingReindexJob.status.in_(
                    [ReindexJobStatus.QUEUED, ReindexJobStatus.RUNNING]
                )
            )
        )).all()
    )
    item_workspaces = set(
        (await session.scalars(
            select(EmbeddingWorkItem.workspace_id).where(
                EmbeddingWorkItem.state.in_(["QUEUED", "WAITING_QUOTA", "RUNNING"])
            )
        )).all()
    )
    candidates: list[IndexCandidate] = []
    for name in names:
        version = by_index.get(name)
        if version is None:
            candidates.append(IndexCandidate(name, None, None, "unknown", None))
            continue
        workspace = workspaces.get(version.workspace_id)
        candidates.append(
            IndexCandidate(
                index_name=name,
                version_id=str(version.id),
                workspace_id=str(version.workspace_id),
                state=version.status,
                age_hours=_age_hours(version.created_at),
                referenced_by_work_item=version.workspace_id in item_workspaces,
                active=workspace is not None
                and workspace.active_embedding_index_version_id == version.id,
                pending_or_running=version.id in busy_versions
                or (
                    workspace is not None
                    and workspace.pending_embedding_index_version_id == version.id
                ),
            )
        )
    return candidates


async def acquire_redis_lock(redis: Redis) -> bool:
    return bool(await redis.set(GC_LOCK_KEY, "held", nx=True, ex=GC_LOCK_TTL_SECONDS))


async def release_redis_lock(redis: Redis) -> None:
    await redis.delete(GC_LOCK_KEY)


async def record_audit(
    session: AsyncSession,
    *,
    mode: str,
    correlation_id: str,
    report,
    pairs: list,
) -> None:
    from app.infrastructure.elasticsearch.gc import POLICY_VERSION

    run = IndexGcRun(
        mode=mode,
        policy_version=POLICY_VERSION,
        correlation_id=correlation_id,
        candidates=report.candidates,
        deletions=report.deleted,
        errors=report.errors,
        finished_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()
    for candidate, decision in pairs:
        deleted = decision.index_name in set(report.deleted_names)
        session.add(
            IndexGcItem(
                run_id=run.id,
                index_name=decision.index_name,
                version_id=_as_uuid(candidate.version_id),
                state=candidate.state,
                age_hours=candidate.age_hours,
                decision=decision.decision,
                reason=decision.reason,
                deleted_at=datetime.now(UTC) if deleted else None,
            )
        )
    await session.commit()


def _as_uuid(value) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (ValueError, AttributeError, TypeError):
        return None


def make_context():
    settings = get_settings()
    es = Elasticsearch(settings.elasticsearch_url)
    redis = Redis.from_url(settings.redis_url, socket_timeout=2)
    return settings, es, redis
