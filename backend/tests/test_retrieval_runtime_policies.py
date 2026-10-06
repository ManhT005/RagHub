from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from raghub_core.api import RetrievalScope, RetrieveContextUseCase
from raghub_core.domain.providers.errors import ProviderRateLimitError
from raghub_core.ports.embedding_quota import QuotaDepletedError
from raghub_core.ports.provider_resolver import EmbeddingRuntime


async def test_query_reserves_interactive_capacity_before_embedding():
    provider = SimpleNamespace(embed_query=AsyncMock(return_value=[1.0, 0.0]))
    runtime = EmbeddingRuntime(provider, "index", 2, quota_scope="project")
    providers = SimpleNamespace(resolve_embedding=AsyncMock(return_value=runtime))
    quota = SimpleNamespace(acquire=AsyncMock(side_effect=QuotaDepletedError(5, 123)))
    use_case = RetrieveContextUseCase(providers, None, None, quota=quota)
    with pytest.raises(ProviderRateLimitError):
        await use_case.retrieve(RetrievalScope(uuid4(), uuid4()), "question", 5)
    assert quota.acquire.call_args.kwargs["background"] is False
    provider.embed_query.assert_not_awaited()


def test_reranker_verifies_snapshot_before_loading_weights(tmp_path, monkeypatch):
    import sys

    from app.infrastructure.ai.local_reranker import LocalCrossEncoderReranker, snapshot_sha256

    (tmp_path / "model.safetensors").write_bytes(b"fixture weights")
    loaded = []

    def cross_encoder(path, **kwargs):
        loaded.append((path, kwargs))
        return object()

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(CrossEncoder=cross_encoder)
    )
    invalid = LocalCrossEncoderReranker(snapshot_path=str(tmp_path), expected_sha256="0" * 64)
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        invalid._load()
    assert not loaded
    valid = LocalCrossEncoderReranker(
        snapshot_path=str(tmp_path), expected_sha256=snapshot_sha256(tmp_path)
    )
    valid._load()
    assert loaded[0][1]["trust_remote_code"] is False


@pytest.mark.parametrize("failure", ["auth", "unavailable", "quota"])
async def test_pool_failover_preserves_shared_quota_and_marks_auth_failures(failure):
    from raghub_core.domain.providers.errors import (
        ProviderAuthenticationError,
        ProviderUnavailableError,
    )

    from app.infrastructure.pool_embedding import PoolEmbeddingProvider

    error = {
        "auth": ProviderAuthenticationError(),
        "unavailable": ProviderUnavailableError(),
        "quota": ProviderRateLimitError(),
    }[failure]
    first = SimpleNamespace(metadata=None, embed_query=AsyncMock(side_effect=error))
    second = SimpleNamespace(metadata=None, embed_query=AsyncMock(return_value=[1.0, 0.0]))
    credentials = [SimpleNamespace(enabled=True, unhealthy=False) for _ in range(2)]
    session = SimpleNamespace(flush=AsyncMock())
    pool = PoolEmbeddingProvider([first, second], credentials, session)
    if failure == "quota":
        with pytest.raises(ProviderRateLimitError):
            await pool.embed_query("question")
        second.embed_query.assert_not_awaited()
    else:
        assert await pool.embed_query("question") == [1.0, 0.0]
    assert credentials[0].unhealthy is (failure == "auth")


async def test_corrupt_semantic_snapshot_fails_before_pool_or_provider_resolution():
    from app.modules.ai_providers.pools import FingerprintMismatchError
    from app.modules.ai_providers.resolver import ProviderResolver

    resolver = ProviderResolver.__new__(ProviderResolver)
    resolver.embedding_pool_for_version = AsyncMock()
    config = SimpleNamespace(capability="EMBEDDING")
    version = SimpleNamespace(
        provider_type="OLLAMA",
        model="model",
        base_url="http://localhost:11434",
        dimension=2,
        config_json={},
        embedding_fingerprint_v2="corrupt",
    )
    with pytest.raises(FingerprintMismatchError):
        await resolver._embedding_provider(config, version)
    resolver.embedding_pool_for_version.assert_not_awaited()
