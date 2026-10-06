from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.infrastructure.embedding_execution import ExecutionPreference, resolve_policy
from app.modules.ai_providers import workspace_ai_router as router


async def test_speed_save_requires_permission_and_does_not_change_model(monkeypatch):
    workspace_id = uuid4()
    item = SimpleNamespace(
        id=workspace_id, embedding_execution_config={}, active_embedding_index_version_id=uuid4()
    )
    context = SimpleNamespace(organization_id=uuid4())
    session = SimpleNamespace(commit=AsyncMock())
    permission = AsyncMock()
    monkeypatch.setattr(router, "require_workspace_permission", permission)
    monkeypatch.setattr(router, "workspace", AsyncMock(return_value=item))
    policy = resolve_policy(
        Settings(_env_file=None, rag_embedding_max_inflight_hard_cap=2),
        "OPENAI_COMPATIBLE",
        workspace_options={"profile": "fast"},
    )
    monkeypatch.setattr(router, "policy_for_workspace", AsyncMock(return_value=policy))
    before_model = item.active_embedding_index_version_id
    result = await router.change_embedding_runtime(
        workspace_id, ExecutionPreference(profile="fast"), context, session
    )
    assert permission.await_args_list[0].args[2] == "ai.change_embedding"
    assert result["effective_max_inflight"] == 2
    assert item.active_embedding_index_version_id == before_model
    session.commit.assert_awaited_once()
    permission.side_effect = AppError("FORBIDDEN", "Denied", status_code=403)
    session.commit.reset_mock()
    with pytest.raises(AppError):
        await router.change_embedding_runtime(
            workspace_id, ExecutionPreference(profile="fast"), context, session
        )
    session.commit.assert_not_awaited()


async def test_custom_preference_above_effective_limit_is_not_saved(monkeypatch):
    item = SimpleNamespace(id=uuid4(), embedding_execution_config={"profile": "balanced"})
    session = SimpleNamespace(commit=AsyncMock())
    context = SimpleNamespace(organization_id=uuid4())
    monkeypatch.setattr(router, "require_workspace_permission", AsyncMock())
    monkeypatch.setattr(router, "workspace", AsyncMock(return_value=item))
    policy = resolve_policy(
        Settings(_env_file=None, rag_embedding_max_inflight_hard_cap=2),
        "OPENAI_COMPATIBLE",
        workspace_options={"profile": "fast"},
    )
    monkeypatch.setattr(router, "policy_for_workspace", AsyncMock(return_value=policy))
    with pytest.raises(AppError) as exc:
        await router.change_embedding_runtime(
            item.id,
            ExecutionPreference(profile="custom", max_inflight_requests=4),
            context,
            session,
        )
    assert exc.value.code == "EMBEDDING_EXECUTION_LIMIT"
    assert item.embedding_execution_config == {"profile": "balanced"}
    session.commit.assert_not_awaited()
