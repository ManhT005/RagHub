"""Index GC runner: inventory, classify, audit, bounded apply.

Only --apply deletes, and only after re-reading each candidate's
protection immediately before its delete. The run stops the batch on the
first state change or delete error. A distributed Redis lock serializes
concurrent runs.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.infrastructure.elasticsearch.gc import (
    GcDecision,
    GcPolicy,
    IndexCandidate,
    classify,
)

GC_LOCK_KEY = "lock:index-gc"
GC_LOCK_TTL_SECONDS = 600
APPLY_BATCH_LIMIT = 10


@dataclass
class GcReport:
    mode: str
    candidates: int
    kept: int
    deleted: int
    reported: int
    errors: int
    decisions: list[GcDecision] = field(default_factory=list)
    deleted_names: list[str] = field(default_factory=list)


class GcLockBusyError(Exception):
    pass


class GcRunner:
    def __init__(
        self,
        *,
        load_candidates: Callable[[], Awaitable[list[IndexCandidate]]],
        delete_index: Callable[[str], Awaitable[None]],
        recheck: Callable[[str | None], Awaitable[IndexCandidate | None]],
        record_run: Callable[[GcReport, str, list], Awaitable[None]],
        acquire_lock: Callable[[], Awaitable[bool]],
        release_lock: Callable[[], Awaitable[None]],
        policy: GcPolicy | None = None,
        batch_limit: int = APPLY_BATCH_LIMIT,
    ) -> None:
        self.load_candidates = load_candidates
        self.delete_index = delete_index
        self.recheck = recheck
        self.record_run = record_run
        self.acquire_lock = acquire_lock
        self.release_lock = release_lock
        self.policy = policy or GcPolicy()
        self.batch_limit = batch_limit

    async def run(self, *, apply: bool, correlation_id: str) -> GcReport:
        if not await self.acquire_lock():
            raise GcLockBusyError("Another index GC run holds the lock.")
        try:
            candidates = await self.load_candidates()
            decisions = classify(candidates, policy=self.policy)
            report = GcReport(
                mode="apply" if apply else "dry-run",
                candidates=len(candidates),
                kept=sum(1 for d in decisions if d.decision == "keep"),
                deleted=0,
                reported=sum(1 for d in decisions if d.decision == "report"),
                errors=0,
                decisions=decisions,
            )
            if apply:
                await self._apply(decisions, report)
            by_index = {c.index_name: c for c in candidates}
            pairs = [(by_index[d.index_name], d) for d in decisions if d.index_name in by_index]
            await self.record_run(report, correlation_id, pairs)
            return report
        finally:
            await self.release_lock()

    async def _apply(self, decisions: list[GcDecision], report: GcReport) -> None:
        removed = 0
        for decision in decisions:
            if decision.decision != "delete" or removed >= self.batch_limit:
                continue
            current = await self.recheck(decision.index_name)
            if current is None or _protective(current):
                report.errors += 1
                break  # state changed under us: stop the batch
            try:
                await self.delete_index(decision.index_name)
            except Exception:
                report.errors += 1
                break
            removed += 1
            report.deleted_names.append(decision.index_name)
        report.deleted = removed


def _protective(candidate: IndexCandidate) -> bool:
    return candidate.active or candidate.pending_or_running or candidate.referenced_by_work_item
