from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.infrastructure.provider_credentials import resolve_provider_secret
from app.modules.ai_providers.bootstrap import ProviderBootstrapService
from app.modules.ai_providers.control_schemas import ConnectionPatch
from app.modules.ai_providers.control_service import ProviderControlService, connection_response
from app.modules.ai_providers.crypto import ProviderSecretCipher
from app.modules.organizations.models import Organization


def test_credentials_are_connection_owned_even_for_shared_runtime_and_multiple_accounts(
    monkeypatch,
):
    monkeypatch.setenv("GEMINI_API_KEY", "never-use-global")
    cipher = ProviderSecretCipher("credential-isolation-test-only")
    connections = [
        SimpleNamespace(catalog_id=brand, encrypted_secret=cipher.encrypt(f"key-{i}"))
        for i, brand in enumerate(["groq", "openrouter", "cerebras", "gemini", "gemini"])
    ]
    models = [
        SimpleNamespace(connection=connection, provider_type="OPENAI_COMPATIBLE")
        for connection in connections
    ]
    assert [resolve_provider_secret(model, cipher) for model in models] == [
        f"key-{i}" for i in range(5)
    ]
    connections[0].encrypted_secret = cipher.encrypt("rotated")
    assert resolve_provider_secret(models[0], cipher) == "rotated"
    assert resolve_provider_secret(models[1], cipher) == "key-1"
    connections[0].encrypted_secret = None
    assert resolve_provider_secret(models[0], cipher) is None
    assert resolve_provider_secret(models[4], cipher) == "key-4"


@pytest.mark.integration
async def test_bootstrap_is_idempotent_and_never_overwrites_manual_rotation(isolated_sessions):
    settings = Settings(
        _env_file=None,
        provider_master_key="credential-isolation-test-only",
        openai_api_key="initial-key",
        gemini_api_key="gemini-key",
    )
    async with isolated_sessions() as session:
        organization = Organization(name="Bootstrap", slug="credential-bootstrap")
        session.add(organization)
        await session.flush()
        bootstrap = ProviderBootstrapService(session, settings)
        first = await bootstrap.import_env(organization.id)
        assert len(first) == 2
        await session.commit()
        openai = next(item for item in first if item.catalog_id == "openai")
        openai.encrypted_secret = bootstrap.cipher.encrypt("manual-rotation")
        await session.commit()
        assert await bootstrap.import_env(organization.id) == []
        await session.commit()
        assert bootstrap.cipher.decrypt(openai.encrypted_secret) == "manual-rotation"
        with pytest.raises(AppError) as error:
            await ProviderControlService(session).update(
                organization.id, openai.id, ConnectionPatch(catalog_id="compatible")
            )
        assert error.value.code == "PROVIDER_IDENTITY_IMMUTABLE"
        assert "encrypted_secret" not in connection_response(openai).model_dump()
