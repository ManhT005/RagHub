from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from raghub_core.domain.providers.contracts import RerankItem, RerankResult

from app.core.exceptions import AppError
from app.modules.ai_providers.schemas import RerankOptions
from app.modules.ai_providers.service import ProviderConfigService
from app.modules.ai_providers.workspace_ai_router import RerankSelection, change_rerank


@pytest.mark.parametrize(
    "values",
    [
        {"candidate_limit": 201},
        {"top_n": 0},
        {"candidate_limit": 3, "top_n": 4},
        {"timeout_seconds": float("inf")},
    ],
)
def test_rerank_settings_are_bounded(values):
    with pytest.raises(ValidationError):
        RerankOptions(**values)


async def test_rerank_binding_checks_health_and_does_not_stage_embedding(monkeypatch):
    from app.modules.ai_providers import workspace_ai_router as router

    workspace = SimpleNamespace(
        rerank_provider_id=None, rerank_config={}, active_embedding_index_version_id=uuid4()
    )
    original_index = workspace.active_embedding_index_version_id
    monkeypatch.setattr(router, "require_workspace_permission", AsyncMock())
    monkeypatch.setattr(router, "workspace", AsyncMock(return_value=workspace))
    model = SimpleNamespace(
        id=uuid4(),
        capability="RERANK",
        enabled=True,
        availability_status="AVAILABLE",
        connection=SimpleNamespace(enabled=True, status="CONNECTED"),
    )
    monkeypatch.setattr(ProviderConfigService, "get", AsyncMock(return_value=model))
    context = SimpleNamespace(organization_id=uuid4())
    session = SimpleNamespace(commit=AsyncMock())
    await change_rerank(uuid4(), RerankSelection(model_id=model.id), context, session)
    assert workspace.rerank_provider_id == model.id
    assert workspace.active_embedding_index_version_id == original_index
    model.capability = "CHAT"
    with pytest.raises(AppError):
        await change_rerank(uuid4(), RerankSelection(model_id=model.id), context, session)
    await change_rerank(uuid4(), RerankSelection(model_id=None), context, session)
    assert workspace.rerank_provider_id is None


async def test_rerank_health_probe_uses_contract_not_chat_stream():
    from app.modules.ai_providers.crypto import ProviderSecretCipher
    from app.modules.ai_providers.models import ProviderConfig

    config = ProviderConfig(
        id=uuid4(),
        organization_id=uuid4(),
        name="reranker",
        model="rerank-3",
        capability="RERANK",
        provider_type="VOYAGE",
        enabled=True,
        config_json={},
    )
    service = object.__new__(ProviderConfigService)
    service.session = SimpleNamespace(commit=AsyncMock())
    service.get = AsyncMock(return_value=config)
    service.cipher = ProviderSecretCipher("test-provider-master-key")
    rerank = AsyncMock(
        return_value=RerankResult([RerankItem(0, 0.9), RerankItem(1, 0.1)], "m", "p")
    )
    service.registry = SimpleNamespace(create=lambda *_: SimpleNamespace(rerank=rerank))
    result = await service.test(config.organization_id, config.id)
    assert result["capability"] == "RERANK" and config.availability_status == "AVAILABLE"
    rerank.assert_awaited_once()
