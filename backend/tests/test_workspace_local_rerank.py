from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from raghub_core.domain.retrieval.models import RetrievalScope

from app.core.exceptions import AppError
from app.infrastructure import rerank
from app.infrastructure.ai import workspace_reranker
from app.infrastructure.ai.local_reranker import LocalRerankProvider, snapshot_sha256
from app.modules.ai_providers import local_manager, workspace_ai_router
from app.modules.ai_providers.local_catalog import LOCAL_RERANK_ID, local_spec
from app.modules.ai_providers.local_manager import LocalModelManager
from app.modules.ai_providers.local_models import LocalModelDownload
from app.modules.ai_providers.workspace_ai_router import RerankSelection
from app.modules.organizations.models import Organization


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "provider"},
        {"mode": "local", "model_id": uuid4()},
        {"mode": "off", "model_id": uuid4()},
        {"mode": "other"},
    ],
)
def test_mode_rejects_ambiguous_bindings(payload):
    with pytest.raises(ValidationError):
        RerankSelection(**payload)


async def test_local_binding_requires_installed_model_and_leaves_index_untouched(monkeypatch):
    item = SimpleNamespace(
        rerank_config={}, rerank_provider_id=uuid4(), active_embedding_index_version_id=uuid4()
    )
    original_index = item.active_embedding_index_version_id
    monkeypatch.setattr(workspace_ai_router, "require_workspace_permission", AsyncMock())
    monkeypatch.setattr(workspace_ai_router, "workspace", AsyncMock(return_value=item))
    state = {"ready": False}
    monkeypatch.setattr(
        workspace_ai_router, "local_installation", AsyncMock(return_value=(state, None))
    )
    session = SimpleNamespace(commit=AsyncMock())
    context = SimpleNamespace(organization_id=uuid4())
    payload = RerankSelection(mode="local", candidate_limit=12, top_n=5, timeout_seconds=10)
    with pytest.raises(AppError) as error:
        await workspace_ai_router.change_rerank(uuid4(), payload, context, session)
    assert error.value.code == "LOCAL_RERANK_NOT_READY"
    session.commit.assert_not_awaited()
    state["ready"] = True
    await workspace_ai_router.change_rerank(uuid4(), payload, context, session)
    assert item.rerank_config["mode"] == "local" and item.rerank_provider_id is None
    assert item.active_embedding_index_version_id == original_index


async def test_preparation_requires_org_admin_and_queues_curated_model(monkeypatch):
    monkeypatch.setattr(workspace_ai_router, "require_workspace_permission", AsyncMock())
    monkeypatch.setattr(workspace_ai_router, "workspace", AsyncMock())
    start = AsyncMock(return_value={"status": "QUEUED"})
    monkeypatch.setattr(LocalModelManager, "start", start)
    context = SimpleNamespace(
        organization_id=uuid4(), membership=SimpleNamespace(role="WORKSPACE_ADMIN")
    )
    with pytest.raises(AppError) as error:
        await workspace_ai_router.prepare_local_rerank(uuid4(), context, object())
    assert error.value.status_code == 403
    start.assert_not_awaited()
    context.membership.role = "ADMIN"
    await workspace_ai_router.prepare_local_rerank(uuid4(), context, object())
    start.assert_awaited_once_with(context.organization_id, LOCAL_RERANK_ID)


async def test_explicit_off_overrides_global_default_and_local_mode_resolves(monkeypatch):
    monkeypatch.setattr(
        rerank,
        "get_settings",
        lambda: SimpleNamespace(ai_rerank_enabled=True, rag_reranker_enabled=True),
    )
    workspace = SimpleNamespace(rerank_config={"mode": "off"}, rerank_provider_id=None)
    session = SimpleNamespace(scalar=AsyncMock(return_value=workspace))
    installation = AsyncMock(return_value=({"ready": True}, ("/curated", "a" * 64)))
    monkeypatch.setattr(rerank, "local_installation", installation)
    adapter = SimpleNamespace(scores=AsyncMock(return_value=[0.2, 0.9]))
    monkeypatch.setattr(rerank, "local_reranker", Mock(return_value=adapter))
    resolver = rerank.WorkspaceRerankResolver(session, None)
    scope = RetrievalScope(uuid4(), uuid4())
    assert await resolver.resolve_rerank(scope) is None
    installation.assert_not_awaited()
    workspace.rerank_config = {
        "mode": "local",
        "candidate_limit": 12,
        "top_n": 5,
        "timeout_seconds": 10,
    }
    runtime = await resolver.resolve_rerank(scope)
    result = await runtime.provider.rerank(query="query", documents=["first", "second"], top_n=1)
    assert [item.index for item in result.items] == [1]
    assert runtime.candidate_limit == 12 and runtime.timeout_seconds == 10
    installation.assert_awaited_once_with(session, scope.organization_id)


async def test_local_unavailable_degrades_without_loading_weights(monkeypatch):
    monkeypatch.setattr(
        rerank,
        "get_settings",
        lambda: SimpleNamespace(ai_rerank_enabled=True, rag_reranker_enabled=False),
    )
    workspace = SimpleNamespace(rerank_config={"mode": "local"}, rerank_provider_id=None)
    session = SimpleNamespace(scalar=AsyncMock(return_value=workspace))
    monkeypatch.setattr(
        rerank, "local_installation", AsyncMock(return_value=({"ready": False}, None))
    )
    factory = Mock()
    monkeypatch.setattr(rerank, "local_reranker", factory)
    with pytest.raises(RuntimeError, match="not ready"):
        await rerank.WorkspaceRerankResolver(session, None).resolve_rerank(
            RetrievalScope(uuid4(), uuid4())
        )
    factory.assert_not_called()


async def test_curated_download_pins_checksum_and_is_scoped(
    isolated_sessions, tmp_path, monkeypatch
):
    from app.infrastructure.task_queue.celery_app import celery_app

    settings = SimpleNamespace(
        local_ai_download_enabled=True,
        local_ai_model_dir=str(tmp_path),
        rag_reranker_enabled=False,
        ai_rerank_enabled=True,
    )
    monkeypatch.setattr(local_manager, "get_settings", lambda: settings)
    monkeypatch.setattr(workspace_reranker, "get_settings", lambda: settings)
    monkeypatch.setattr(workspace_reranker, "local_dependencies_available", lambda: True)
    monkeypatch.setattr(celery_app, "send_task", Mock())
    monkeypatch.setattr(local_manager, "download_manifest", lambda _: [("model.safetensors", 4)])
    monkeypatch.setattr(
        local_manager,
        "download_file",
        lambda spec, name, target: Path(target, name).write_bytes(b"safe"),
    )
    async with isolated_sessions() as session:
        org = Organization(name="Rerank", slug=uuid4().hex)
        session.add(org)
        await session.commit()
        manager = LocalModelManager(session)
        await manager.start(org.id, LOCAL_RERANK_ID)
        from sqlalchemy import select

        row = await session.scalar(select(LocalModelDownload))
        await manager.run(row.id)
        assert row.status == "INSTALLED"
        status, paths = await workspace_reranker.local_installation(session, org.id)
        assert status["ready"] and paths[1] == snapshot_sha256(Path(paths[0]))
        assert await manager.start(org.id, LOCAL_RERANK_ID) == {"status": "INSTALLED"}
        other, _ = await workspace_reranker.local_installation(session, uuid4())
        assert not other["ready"]
        Path(paths[0], "model.safetensors").unlink()
        broken, _ = await workspace_reranker.local_installation(session, org.id)
        assert not broken["ready"] and broken["status"] == "FAILED"
        assert await manager.start(org.id, LOCAL_RERANK_ID) == {"status": "QUEUED"}
        await manager.run(row.id)
        repaired, _ = await workspace_reranker.local_installation(session, org.id)
        assert repaired["ready"]


async def test_local_status_reports_missing_extras(monkeypatch):
    monkeypatch.setattr(
        workspace_reranker,
        "get_settings",
        lambda: SimpleNamespace(
            rag_reranker_enabled=False, ai_rerank_enabled=True, local_ai_download_enabled=True
        ),
    )
    monkeypatch.setattr(workspace_reranker, "local_dependencies_available", lambda: False)
    state, paths = await workspace_reranker.local_installation(
        SimpleNamespace(scalar=AsyncMock(return_value=None)), uuid4()
    )
    assert state["status"] == "UNSUPPORTED" and not state["ready"] and paths is None


async def test_local_provider_preserves_duplicate_documents_as_distinct_indices():
    provider = LocalRerankProvider(SimpleNamespace(scores=AsyncMock(return_value=[0.1, 0.9, 0.3])))
    result = await provider.rerank(query="q", documents=["same", "same", "other"], top_n=2)
    assert [item.index for item in result.items] == [1, 2]


def test_rerank_catalog_never_registers_an_embedding_dimension():
    spec = local_spec(LOCAL_RERANK_ID)
    assert spec.capability == "RERANK" and spec.dimension == 0
