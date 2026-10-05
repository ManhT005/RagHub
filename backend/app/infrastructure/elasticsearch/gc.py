"""Index GC policy: inventory, protection, audit. Default dry-run.

Protected forever: the active index, indices of pending/running jobs,
indices referenced by embedding work items, and the two newest completed
versions per workspace. Retention: retired >= 24h, failed >= 7 days.
Unknown raghub_chunks_* names are reported, never deleted.
"""
from __future__ import annotations

from dataclasses import dataclass

POLICY_VERSION = "v1"
RETIRED_RETENTION_HOURS = 24
FAILED_RETENTION_HOURS = 7 * 24
KEEP_RECENT_COMPLETED = 2
INDEX_PREFIX = "raghub_chunks_"


@dataclass(frozen=True)
class IndexCandidate:
    index_name: str
    version_id: str | None
    workspace_id: str | None
    state: str
    age_hours: float | None
    referenced_by_work_item: bool = False
    active: bool = False
    pending_or_running: bool = False


@dataclass(frozen=True)
class GcDecision:
    index_name: str
    decision: str  # keep | delete | report
    reason: str


@dataclass
class GcPolicy:
    retired_retention_hours: float = RETIRED_RETENTION_HOURS
    failed_retention_hours: float = FAILED_RETENTION_HOURS
    keep_recent_completed: int = KEEP_RECENT_COMPLETED
    version: str = POLICY_VERSION


def classify(
    candidates: list[IndexCandidate], *, policy: GcPolicy | None = None
) -> list[GcDecision]:
    policy = policy or GcPolicy()
    recent_kept: dict[str, int] = {}
    ordered = sorted(
        candidates,
        key=lambda c: (c.workspace_id or "", -(c.age_hours or 0)),
    )
    decisions: list[GcDecision] = []
    for candidate in ordered:
        reason = _protect_reason(candidate, recent_kept, policy)
        if reason is not None:
            decisions.append(GcDecision(candidate.index_name, "keep", reason))
            continue
        if candidate.version_id is None:
            decisions.append(GcDecision(candidate.index_name, "report", "unknown-index"))
            continue
        if (
            candidate.state == "RETIRED"
            and (candidate.age_hours or 0) >= policy.retired_retention_hours
        ):
            decisions.append(
                GcDecision(candidate.index_name, "delete", "retired-retention-met")
            )
        elif (
            candidate.state == "FAILED"
            and (candidate.age_hours or 0) >= policy.failed_retention_hours
        ):
            decisions.append(GcDecision(candidate.index_name, "delete", "failed-retention-met"))
        else:
            decisions.append(GcDecision(candidate.index_name, "keep", "retention-not-met"))
    return decisions


def _protect_reason(
    candidate: IndexCandidate, recent_kept: dict[str, int], policy: GcPolicy
) -> str | None:
    if candidate.active:
        return "active-index"
    if candidate.pending_or_running:
        return "pending-running-job"
    if candidate.referenced_by_work_item:
        return "work-item-reference"
    if candidate.state == "COMPLETED" and candidate.workspace_id:
        kept = recent_kept.get(candidate.workspace_id, 0)
        if kept < policy.keep_recent_completed:
            recent_kept[candidate.workspace_id] = kept + 1
            return "recent-completed-version"
    return None
