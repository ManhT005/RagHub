"""Fair scheduling across workspaces: weighted round-robin per priority class.

Priority: query embedding > upload > reindex. Inside one class, workspaces
take turns (A/B/C/A) so a single workspace flood cannot starve the others.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

KIND_PRIORITY = {"query": 0, "upload": 1, "reindex": 2}


@dataclass(frozen=True)
class WorkItemRef:
    id: UUID
    workspace_id: UUID
    kind: str


def pick_order(
    items: list[WorkItemRef], *, last_served: dict[str, UUID] | None = None
) -> list[UUID]:
    """Order ready items fairly. `last_served` maps kind -> workspace served last."""
    cursor: dict[str, UUID] = dict(last_served or {})
    ordered: list[UUID] = []
    by_kind: dict[str, list[WorkItemRef]] = {}
    for item in items:
        by_kind.setdefault(item.kind, []).append(item)
    for kind in sorted(by_kind, key=lambda k: KIND_PRIORITY.get(k, 99)):
        group = list(by_kind[kind])
        workspaces: list[UUID] = []
        for item in group:
            if item.workspace_id not in workspaces:
                workspaces.append(item.workspace_id)
        start = 0
        if cursor.get(kind) in workspaces:
            start = (workspaces.index(cursor[kind]) + 1) % len(workspaces)
        rotation = workspaces[start:] + workspaces[:start]
        for workspace_id in rotation:
            for item in group:
                if item.workspace_id == workspace_id and item.id not in ordered:
                    ordered.append(item.id)
        if rotation:
            cursor[kind] = rotation[-1]
    return ordered
