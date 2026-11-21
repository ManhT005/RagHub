import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from raghub_core.domain.retrieval.models import RetrievalScope
from raghub_core.ports.reranker import RerankerTimeoutError

from app.infrastructure import rerank
from app.infrastructure.ai import qwen_reranker as qwen
from app.modules.ai_providers.local_catalog import QWEN_RERANK_ID, local_spec
from app.modules.ai_providers.workspace_ai_router import RerankSelection


def test_qwen_is_curated_rerank_only_and_large_manifest_is_bounded():
    spec = local_spec(QWEN_RERANK_ID)
    assert spec.repo == qwen.MODEL_ID and spec.revision == qwen.MODEL_REVISION
    assert spec.capability == "RERANK" and spec.dimension == 0
    assert 1_200_000_000 < spec.max_bytes <= 1_500_000_000
    assert (
        RerankSelection(mode="local", local_model_id=QWEN_RERANK_ID).local_model_id
        == QWEN_RERANK_ID
    )
    with pytest.raises(ValidationError):
        RerankSelection(mode="local", local_model_id="untrusted/repo")


def test_qwen_verifies_snapshot_before_loading_dependencies(tmp_path):
    adapter = qwen.QwenReranker(str(tmp_path), "not-a-checksum", 20)
    with pytest.raises(RuntimeError, match="not pinned"):
        adapter._load()
    (tmp_path / "model.safetensors").write_bytes(b"model")
    adapter.expected_sha256 = "a" * 64
    with pytest.raises(RuntimeError, match="mismatch"):
        adapter._load()


def test_qwen_input_preserves_yes_no_suffix_and_bounds_length():
    class Tokenizer:
        def __call__(self, texts, **kwargs):
            self.kwargs = kwargs
            return {
                "input_ids": [[1] * min(len(t), kwargs["max_length"]) for t in texts],
                "attention_mask": [[1] for _ in texts],
            }

        def pad(self, inputs, **kwargs):
            assert "attention_mask" not in inputs
            return inputs

    adapter = qwen.QwenReranker("unused", "a" * 64, 20)
    adapter._tokenizer = Tokenizer()
    adapter._prefix, adapter._suffix = [5, 6], [7, 8]
    inputs = adapter._inputs("Vietnamese query", ["x" * 5000, "short"])
    for ids in inputs["input_ids"]:
        assert ids[:2] == [5, 6] and ids[-2:] == [7, 8]
        assert len(ids) <= qwen.MAX_LENGTH
    assert adapter._tokenizer.kwargs["add_special_tokens"] is False


async def test_qwen_scores_validate_and_timeout_signals_cancel(monkeypatch):
    adapter = qwen.QwenReranker("unused", "a" * 64, 0.01)
    assert await adapter.scores("q", []) == []
    monkeypatch.setattr(adapter, "_predict", lambda *args: [float("nan")])
    with pytest.raises(RuntimeError, match="invalid scores"):
        await adapter.scores("q", ["doc"])
    stopped = threading.Event()

    def blocked(query, docs, cancelled):
        cancelled.wait(1)
        stopped.set()
        return [0.5]

    monkeypatch.setattr(adapter, "_predict", blocked)
    with pytest.raises(RerankerTimeoutError):
        await adapter.scores("q", ["doc"])
    assert await __import__("asyncio").to_thread(stopped.wait, 1)


async def test_resolver_selects_qwen_explicitly_and_preserves_options(monkeypatch):
    monkeypatch.setattr(rerank, "get_settings", lambda: SimpleNamespace(ai_rerank_enabled=True))
    workspace = SimpleNamespace(
        rerank_provider_id=None,
        rerank_config={
            "mode": "local",
            "local_model_id": QWEN_RERANK_ID,
            "candidate_limit": 30,
            "top_n": 10,
            "timeout_seconds": 30,
        },
    )
    install = AsyncMock(
        return_value=({"ready": True, "model": qwen.MODEL_ID}, ("/pinned", "a" * 64))
    )
    monkeypatch.setattr(rerank, "local_installation", install)

    def factory(**kwargs):
        return SimpleNamespace(scores=AsyncMock(return_value=[0.2, 0.8]))

    monkeypatch.setattr(qwen, "qwen_reranker", factory)
    scope = RetrievalScope(uuid4(), uuid4())
    session = SimpleNamespace(scalar=AsyncMock(return_value=workspace))
    runtime = await rerank.WorkspaceRerankResolver(session, None).resolve_rerank(scope)
    install.assert_awaited_once_with(session, scope.organization_id, QWEN_RERANK_ID)
    result = await runtime.provider.rerank(query="q", documents=["a", "b"], top_n=1)
    assert result.model == qwen.MODEL_ID and result.items[0].index == 1
    assert runtime.candidate_limit == 30 and runtime.top_n == 10


async def test_qwen_binding_schedules_warmup_after_save_without_reindex(monkeypatch):
    from fastapi import BackgroundTasks

    from app.modules.ai_providers import workspace_ai_router as router

    workspace = SimpleNamespace(
        rerank_provider_id=None, rerank_config={}, active_embedding_index_version_id=uuid4()
    )
    index_id = workspace.active_embedding_index_version_id
    monkeypatch.setattr(router, "workspace", AsyncMock(return_value=workspace))
    monkeypatch.setattr(router, "require_workspace_permission", AsyncMock())
    monkeypatch.setattr(
        router,
        "local_installation",
        AsyncMock(return_value=({"ready": True}, ("/pinned", "a" * 64))),
    )
    from unittest.mock import Mock

    adapter = SimpleNamespace(warmup=Mock())
    factory = Mock(return_value=adapter)
    monkeypatch.setattr(qwen, "qwen_reranker", factory)
    tasks = BackgroundTasks()
    session = SimpleNamespace(commit=AsyncMock())
    context = SimpleNamespace(organization_id=uuid4())
    payload = RerankSelection(mode="local", local_model_id=QWEN_RERANK_ID, timeout_seconds=30)
    await router.change_rerank(uuid4(), payload, context, session, tasks)
    factory.assert_called_once_with(
        snapshot_path="/pinned", expected_sha256="a" * 64, timeout_seconds=30
    )
    assert len(tasks.tasks) == 1 and tasks.tasks[0].func == adapter.warmup
    adapter.warmup.assert_not_called()
    assert workspace.active_embedding_index_version_id == index_id
    assert workspace.rerank_config["local_model_id"] == QWEN_RERANK_ID
