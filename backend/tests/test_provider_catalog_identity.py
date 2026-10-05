import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from pydantic import ValidationError

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.core.exceptions import AppError
from app.modules.ai_providers.catalog import connection_catalog_id
from app.modules.ai_providers.control_schemas import ConnectionInput, ConnectionPatch
from app.modules.ai_providers.control_service import ProviderControlService, model_response
from app.modules.workspaces.summary import summary_data


def test_explicit_custom_identity_overrides_openai_endpoint():
    connection = SimpleNamespace(
        catalog_id="compatible",
        provider_type="OPENAI_COMPATIBLE",
        base_url="https://api.openai.com/v1",
        name="OpenAI",
        status="CONNECTED",
        enabled=True,
    )
    assert connection_catalog_id(connection) == "compatible"
    connection.catalog_id = None
    assert connection_catalog_id(connection) == "openai"
    connection.base_url = "https://custom.example/v1"
    assert connection_catalog_id(connection) == "compatible"


def test_catalog_validation_rejects_mismatch_unknown_and_coming_soon():
    with pytest.raises(ValidationError):
        ConnectionInput(name="wrong", catalog_id="gemini", provider_type="OLLAMA")
    for catalog_id in ("missing", "anthropic"):
        with pytest.raises(AppError):
            ConnectionInput(name="wrong", catalog_id=catalog_id, provider_type="OPENAI_COMPATIBLE")
    with pytest.raises(ValidationError):
        ConnectionInput(name="Custom", catalog_id="compatible", provider_type="OPENAI_COMPATIBLE")
    assert (
        ConnectionInput(
            name="OpenAI", catalog_id="openai", provider_type="OPENAI_COMPATIBLE"
        ).base_url
        == "https://api.openai.com/v1"
    )


def test_catalog_patch_cannot_clear_identity():
    assert ConnectionPatch().catalog_id is None
    with pytest.raises(ValidationError):
        ConnectionPatch(catalog_id=None)
    with pytest.raises(AppError):
        ConnectionPatch(catalog_id="anthropic")


async def test_mismatched_patch_returns_a_contract_error_before_any_mutation():
    from unittest.mock import AsyncMock

    service = object.__new__(ProviderControlService)
    service.get = AsyncMock(
        return_value=SimpleNamespace(
            provider_type="OLLAMA",
            catalog_id="ollama",
            base_url="http://ollama:11434",
        )
    )
    with pytest.raises(AppError) as error:
        await service.update(None, None, ConnectionPatch(catalog_id="gemini"))
    assert error.value.status_code == 422


def test_identity_survives_model_and_workspace_serialization():
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.modules.ai_providers.models import ProviderConfig, ProviderConnection

    connection = ProviderConnection(
        catalog_id="compatible",
        provider_type="OPENAI_COMPATIBLE",
        name="Custom",
        enabled=True,
        status="CONNECTED",
    )
    config = ProviderConfig(
        id=uuid4(),
        connection=connection,
        model="arbitrary-model",
        name="model",
        provider_type="OPENAI_COMPATIBLE",
        capability="EMBEDDING",
        dimension=384,
        availability_status="AVAILABLE",
        enabled=True,
    )
    assert model_response(config).provider_catalog_id == "compatible"
    workspace = SimpleNamespace(
        id=uuid4(),
        name="Knowledge",
        slug="knowledge",
        organization_id=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=None,
        chat_provider_id=None,
    )
    version = SimpleNamespace(
        provider_config_id=config.id,
        model=config.model,
        provider_type=config.provider_type,
        dimension=384,
    )
    assert (
        summary_data((workspace, 3, 10, None, 1, version, config, None, None))["embedding_model"][
            "provider_catalog_id"
        ]
        == "compatible"
    )


def test_migration_upgrades_existing_connections_and_downgrades():
    path = Path(__file__).parents[1] / "alembic/versions/20261004_0016_provider_catalog_identity.py"
    spec = importlib.util.spec_from_file_location("catalog_identity_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with sa.create_engine("sqlite://").begin() as connection:
        connection.execute(
            sa.text("CREATE TABLE provider_connections (provider_type TEXT, base_url TEXT)")
        )
        values = [
            ("GOOGLE_GEMINI", None),
            ("OLLAMA", None),
            ("LOCAL_SENTENCE_TRANSFORMER", None),
            ("OPENAI_COMPATIBLE", "https://api.openai.com/v1/"),
            ("OPENAI_COMPATIBLE", "https://custom.example/v1"),
            ("OPENAI_COMPATIBLE", None),
            ("UNKNOWN", None),
        ]
        for provider_type, base_url in values:
            connection.execute(
                sa.text("INSERT INTO provider_connections VALUES (:type, :url)"),
                {"type": provider_type, "url": base_url},
            )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert list(connection.scalars(sa.text("SELECT catalog_id FROM provider_connections"))) == [
            "gemini",
            "ollama",
            "sentence-transformer",
            "openai",
            "compatible",
            "compatible",
            None,
        ]
        migration.downgrade()
        assert [
            column["name"] for column in sa.inspect(connection).get_columns("provider_connections")
        ] == ["provider_type", "base_url"]
