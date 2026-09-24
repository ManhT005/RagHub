import uuid
from types import SimpleNamespace

from app.modules.ai_providers.service import embedding_fingerprint, workspace_index_name


def test_embedding_identity_includes_provider_model_and_dimension() -> None:
    base = SimpleNamespace(provider_type="OPENAI_COMPATIBLE", model="model-a", dimension=768)
    changed_model = SimpleNamespace(
        provider_type="OPENAI_COMPATIBLE", model="model-b", dimension=768
    )
    changed_dimension = SimpleNamespace(
        provider_type="OPENAI_COMPATIBLE", model="model-a", dimension=1536
    )

    assert embedding_fingerprint(base) != embedding_fingerprint(changed_model)  # type: ignore[arg-type]
    assert embedding_fingerprint(base) != embedding_fingerprint(changed_dimension)  # type: ignore[arg-type]


def test_physical_index_name_is_workspace_scoped_and_versioned() -> None:
    workspace_id, version_id = uuid.uuid4(), uuid.uuid4()

    name = workspace_index_name(workspace_id, version_id)

    assert workspace_id.hex in name
    assert version_id.hex[:12] in name
