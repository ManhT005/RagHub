from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.core.config import Settings
from app.modules.ai_providers.work_items import WorkItemRepository


async def test_claim_uses_locked_conditional_row_and_respects_active_limit():
    item = SimpleNamespace(state="QUEUED", attempts=0, available_at=None)
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[uuid4(), uuid4(), 0, item]), flush=AsyncMock()
    )
    repo = WorkItemRepository(session, Settings())
    assert await repo.claim(uuid4(), now=datetime.now(UTC)) is item
    sql = str(session.scalar.call_args_list[-1].args[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "state IN" in sql and "available_at" in sql
    assert item.state == "RUNNING" and item.attempts == 1

    session.scalar = AsyncMock(side_effect=[uuid4(), uuid4(), 1])
    assert await repo.claim(uuid4()) is None
    assert session.scalar.await_count == 3


async def test_creation_rejects_pending_count_at_configured_boundary():
    import pytest

    session = SimpleNamespace(scalar=AsyncMock(side_effect=[uuid4(), 2]))
    repo = WorkItemRepository(session, Settings(provider_pool_max_pending_jobs_per_workspace=2))
    with pytest.raises(ValueError, match="queue is full"):
        await repo.create(organization_id=uuid4(), workspace_id=uuid4(), pool_id=uuid4())
