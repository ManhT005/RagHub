"""Managed provider pools, fingerprint v2 and compatible failover (offline)."""
from uuid import uuid4

import pytest
from raghub_core.domain.providers.fingerprint import (
    embedding_fingerprint_v2,
    normalize_endpoint,
    quota_scope,
)

from app.modules.ai_providers.pools import (
    FingerprintMismatchError,
    LegacyProviderRow,
    PoolCredential,
    PoolExhaustedError,
    backfill_pool_for_config,
    classify_provider_failure,
    resolve_pool_for_fingerprint,
    select_healthy_credential,
)


def _row(**overrides):
    base = {
        "id": uuid4(),
        "organization_id": uuid4(),
        "provider_type": "GOOGLE_GEMINI",
        "capability": "EMBEDDING",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "text-embedding-004",
        "dimension": 768,
        "encrypted_secret": "ciphertext-blob",
        "config_json": {"task_type": "RETRIEVAL_DOCUMENT"},
    }
    base.update(overrides)
    return LegacyProviderRow(**base)


def test_fingerprint_v2_ignores_secret_quota_timeout_and_config_id():
    first = backfill_pool_for_config(_row(), pool_id=uuid4())
    second = backfill_pool_for_config(
        _row(
            config_json={
                "task_type": "RETRIEVAL_DOCUMENT",
                "connect_timeout": 99,
                "read_timeout": 99,
                "max_attempts": 5,
                "quota_project": "other-project",
            },
            encrypted_secret="different-blob",
        ),
        pool_id=uuid4(),
    )
    assert first.fingerprint_v2 == second.fingerprint_v2


def test_fingerprint_v2_changes_with_model_dimension_or_endpoint():
    base = {"provider_type": "OPENAI_COMPATIBLE", "base_url": "https://x/v1", "model": "m"}
    assert embedding_fingerprint_v2(dimension=1, **base) != embedding_fingerprint_v2(
        dimension=2, **base
    )
    assert embedding_fingerprint_v2(
        dimension=1, model="a", provider_type="OPENAI_COMPATIBLE", base_url="https://x/v1"
    ) != embedding_fingerprint_v2(
        dimension=1, model="b", provider_type="OPENAI_COMPATIBLE", base_url="https://x/v1"
    )
    assert embedding_fingerprint_v2(dimension=1, **base) != embedding_fingerprint_v2(
        dimension=1,
        provider_type="OPENAI_COMPATIBLE",
        base_url="https://y/v1",
        model="m",
    )


def test_normalize_endpoint():
    assert normalize_endpoint("https://Example.COM:443/v1/") == "https://example.com/v1"
    assert normalize_endpoint("http://Example.COM:80/v1") == "http://example.com/v1"
    assert normalize_endpoint(None) == ""


def test_quota_scope_shared_inside_one_project():
    same_a = quota_scope(provider_type="GOOGLE_GEMINI", model="m", project="proj-1")
    same_b = quota_scope(provider_type="GOOGLE_GEMINI", model="m", project="PROJ-1")
    other = quota_scope(provider_type="GOOGLE_GEMINI", model="m", project="proj-2")
    assert same_a == same_b
    assert same_a != other


def test_backfill_copies_ciphertext_verbatim():
    row = _row(encrypted_secret="gAAAAAB-opaque")
    pool = backfill_pool_for_config(row, pool_id=uuid4())
    assert pool.primary_encrypted_secret == "gAAAAAB-opaque"
    assert pool.organization_id == row.organization_id
    assert pool.quota_scope.startswith("GOOGLE_GEMINI:text-embedding-004:")


def test_select_healthy_credential_skips_bad_ones():
    good, bad, off = (
        PoolCredential(uuid4(), True, False),
        PoolCredential(uuid4(), True, True),
        PoolCredential(uuid4(), False, False),
    )
    assert select_healthy_credential([bad, off, good]) == good
    with pytest.raises(PoolExhaustedError):
        select_healthy_credential([bad, off])
    with pytest.raises(PoolExhaustedError):
        select_healthy_credential([good], exclude_ids={good.id})


def test_resolve_pool_fails_closed_on_mismatch():
    pool_id = uuid4()
    assert resolve_pool_for_fingerprint({"fp": pool_id}, "fp") == pool_id
    with pytest.raises(FingerprintMismatchError):
        resolve_pool_for_fingerprint({"fp": pool_id}, "other")


def test_classify_provider_failure():
    assert classify_provider_failure(401) == "unhealthy"
    assert classify_provider_failure(403) == "unhealthy"
    assert classify_provider_failure(429) == "quota"
    assert classify_provider_failure(500) == "retryable"
    assert classify_provider_failure(None) == "retryable"


def test_migration_chain_is_linked():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).parent.parent / "alembic" / "versions" / "20261005_0023_provider_pools.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0023", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "20261005_0023"
    assert migration.down_revision == "20261005_0022"
    assert callable(migration.upgrade) and callable(migration.downgrade)


def test_facade_exposes_no_credential_listing():
    from app.modules.ai_providers.router import router
    from app.modules.ai_providers.schemas import ProviderConfigResponse

    assert "encrypted_secret" not in ProviderConfigResponse.model_fields
    assert "secret" not in ProviderConfigResponse.model_fields
    for route in router.routes:
        assert "credential" not in getattr(route, "path", "")
