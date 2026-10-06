"""Versioned reindex with validate-before-activate and pointer rollback.

Mapping changes never touch the active index in place: a new versioned
index is built, validated (count/dimension/sample), then the workspace
active pointer swaps atomically. The previous pointer is returned so a
failed gate can roll back without reindexing.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from raghub_core.domain.providers.enums import IndexVersionStatus

from app.modules.ai_providers.models import EmbeddingIndexVersion
from app.modules.workspaces.models import Workspace


def versioned_index_name(base: str, mapping_version: str) -> str:
    suffix = "".join(ch for ch in mapping_version if ch.isalnum()).lower()
    return f"{base}__{suffix}"


def validate_candidate_index(
    client: Any, *, index_name: str, dimension: int, min_docs: int = 1
) -> dict[str, Any]:
    """Check existence, vector dims and document count before activation."""
    if not client.indices.exists(index=index_name):
        return {"ok": False, "reason": "missing-index"}
    mapping = client.indices.get_mapping(index=index_name)
    try:
        props = next(iter(mapping.values()))["mappings"]["properties"]
        dims = props["embedding"]["dims"]
    except (KeyError, StopIteration, TypeError):
        return {"ok": False, "reason": "mapping-mismatch"}
    if dims != dimension:
        return {"ok": False, "reason": f"dimension-mismatch:{dims}!={dimension}"}
    count = client.count(index=index_name).get("count", 0)
    if count < min_docs:
        return {"ok": False, "reason": f"doc-count:{count}<{min_docs}", "count": count}
    return {"ok": True, "count": count, "dimension": dims}


async def activate_index_version(
    session: Any, *, workspace_id: UUID, new_version_id: UUID
) -> UUID | None:
    """Atomically swap the workspace active pointer; return the previous id."""
    workspace = await session.get(Workspace, workspace_id)
    new = await session.get(EmbeddingIndexVersion, new_version_id)
    if workspace is None or new is None:
        raise ValueError("Workspace or index version was not found.")
    if new.workspace_id != workspace.id:
        raise ValueError("Index version belongs to another workspace.")
    previous_id = workspace.active_embedding_index_version_id
    if previous_id is not None and previous_id != new.id:
        old = await session.get(EmbeddingIndexVersion, previous_id)
        if old is not None:
            old.status = IndexVersionStatus.RETIRED
    new.status = IndexVersionStatus.ACTIVE
    new.activated_at = datetime.now(UTC)
    workspace.active_embedding_index_version_id = new.id
    workspace.pending_embedding_index_version_id = None
    await session.commit()
    return previous_id


async def rollback_index_version(
    session: Any, *, workspace_id: UUID, previous_version_id: UUID
) -> None:
    """Point the workspace back at a retained version; demote the bad active."""
    workspace = await session.get(Workspace, workspace_id)
    previous = await session.get(EmbeddingIndexVersion, previous_version_id)
    if workspace is None or previous is None:
        raise ValueError("Workspace or index version was not found.")
    if previous.workspace_id != workspace.id:
        raise ValueError("Index version belongs to another workspace.")
    current_id = workspace.active_embedding_index_version_id
    if current_id is not None and current_id != previous.id:
        bad = await session.get(EmbeddingIndexVersion, current_id)
        if bad is not None:
            bad.status = IndexVersionStatus.FAILED
    previous.status = IndexVersionStatus.ACTIVE
    previous.activated_at = datetime.now(UTC)
    workspace.active_embedding_index_version_id = previous.id
    await session.commit()
