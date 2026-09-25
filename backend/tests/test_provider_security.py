import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import SecretRedactionFilter
from app.modules.ai_providers.router import provider_response
from app.modules.ai_providers.schemas import ProviderConfigInput


def test_provider_response_never_exposes_ciphertext() -> None:
    config = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        name="external",
        provider_type="OPENAI_COMPATIBLE",
        capability="CHAT",
        base_url="https://provider.test/v1",
        model="chat-model",
        dimension=None,
        encrypted_secret="ciphertext-must-not-leak",
        config_json={},
        enabled=True,
        created_at="2026-09-24T00:00:00Z",
        updated_at=None,
    )

    serialized = provider_response(config).model_dump(mode="json")  # type: ignore[arg-type]

    assert serialized["has_secret"] is True
    assert "encrypted_secret" not in serialized
    assert "ciphertext-must-not-leak" not in str(serialized)


@pytest.mark.parametrize(
    "config",
    [
        {"api_key": "secret"},
        {"headers": {"Authorization": "Bearer secret"}},
        {"nested": [{"password": "secret"}]},
    ],
)
def test_provider_config_rejects_secrets_in_public_config(config: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProviderConfigInput(
            name="provider",
            provider_type="OPENAI_COMPATIBLE",
            capability="CHAT",
            model="model",
            config_json=config,
        )


def test_logging_filter_redacts_authorization_and_api_keys() -> None:
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "Authorization=Bearer abc api_key=top-secret",
        (),
        None,
    )

    SecretRedactionFilter().filter(record)

    assert "abc" not in record.getMessage()
    assert "top-secret" not in record.getMessage()
    assert record.getMessage().count("[REDACTED]") == 2


@pytest.mark.parametrize(
    "key",
    ["", "change-me-provider-key", "local-provider-key-change-before-production"],
)
def test_production_rejects_placeholder_provider_master_key(key: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", provider_master_key=key)


def test_production_accepts_dedicated_provider_master_key() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        provider_master_key="a-unique-production-key-with-sufficient-randomness",
    )

    assert settings.app_env == "production"
