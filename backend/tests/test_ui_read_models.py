from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.exceptions import AppError
from app.infrastructure.persistence.index_metadata import MetadataIndexBuilder
from app.modules.ai_providers.models import ProviderConfig, ProviderConnection
from app.modules.ai_providers.workspace_ai_router import available
from app.modules.documents.service import DocumentService
from app.modules.workspaces.summary import summary_data, summary_statement


def test_summary_uses_aggregates_and_active_index_metadata():
    organization_id = uuid4()
    query = str(summary_statement(organization_id).compile(dialect=postgresql.dialect()))
    assert "GROUP BY" in query and "row_number() OVER" in query
    assert "active_embedding_index_version_id" in query and "document_index_metadata" in query
    assert "deleted_at IS NULL" in query
    workspace = SimpleNamespace(
        id=uuid4(),
        name="Workspace",
        slug="workspace",
        organization_id=organization_id,
        created_at=datetime.now(UTC),
        updated_at=None,
        chat_provider_id=None,
    )
    result = summary_data((workspace, 2, None, None, 1, None, None, None, None))
    assert result["document_count"] == 2 and result["chunk_count"] is None
    assert result["status"] == "AI_NOT_CONFIGURED" and "owner" not in result


@pytest.mark.parametrize(
    "status,enabled,connection_status",
    [
        ("UNTESTED", True, "CONNECTED"),
        ("AVAILABLE", False, "CONNECTED"),
        ("AVAILABLE", True, "DEGRADED"),
        ("DISABLED", True, "CONNECTED"),
    ],
)
def test_unavailable_models_cannot_bind(status, enabled, connection_status):
    config = ProviderConfig(
        capability="EMBEDDING",
        enabled=enabled,
        availability_status=status,
        connection=ProviderConnection(enabled=True, status=connection_status),
    )
    with pytest.raises(AppError) as error:
        available(config, "EMBEDDING")
    assert error.value.code == "MODEL_NOT_AVAILABLE"


async def test_builder_persists_metadata_after_index_success_without_switching_pending_model():
    active_id, pending_id, document_id, version_id = (uuid4() for _ in range(4))
    workspace = SimpleNamespace(active_embedding_index_version_id=active_id)
    version = SimpleNamespace(chunk_count=10, indexed_at=None)
    runtime = SimpleNamespace(index_name="pending_index")
    index = SimpleNamespace(chunks=[1, 2, 3])

    async def execute(document, resolver, store, **kwargs):
        await resolver()
        return index

    session = SimpleNamespace(
        scalar=AsyncMock(return_value=pending_id),
        get=AsyncMock(side_effect=[None, workspace]),
        add=lambda value: None,
        commit=AsyncMock(),
    )
    document = SimpleNamespace(
        document_id=document_id,
        version_id=version_id,
        scope=SimpleNamespace(organization_id=uuid4(), workspace_id=uuid4()),
    )
    result = await MetadataIndexBuilder(SimpleNamespace(execute=execute), session).execute(
        document, AsyncMock(return_value=runtime), lambda value: None
    )
    assert result is index and version.chunk_count == 10
    assert session.get.await_count == 2  # pending builds do not rewrite active document metadata
    session.commit.assert_awaited_once()


async def test_document_detail_and_download_do_not_expose_storage_key():
    now = datetime.now(UTC)
    document = SimpleNamespace(
        id=uuid4(), name="a.txt", status="READY", created_at=now, updated_at=now
    )
    version = SimpleNamespace(
        id=uuid4(),
        status="READY",
        mime_type="text/plain",
        size_bytes=7,
        chunk_count=1,
        indexed_at=now,
        checksum="sha256",
        storage_key="private-key",
    )
    job = SimpleNamespace(id=uuid4(), stage="READY", progress=100, attempts=1, error_code=None)
    snapshot = SimpleNamespace(provider_config_id=uuid4(), model="embedding-model", dimension=384)
    service = object.__new__(DocumentService)
    service.repository = SimpleNamespace(
        workspace_exists=AsyncMock(return_value=True),
        list_documents=AsyncMock(return_value=[document]),
        list_document_jobs=AsyncMock(return_value={document.id: (version, job)}),
        embedding_snapshot=AsyncMock(return_value=snapshot),
        find_document=AsyncMock(return_value=document),
        latest_version=AsyncMock(return_value=version),
    )
    service.storage = SimpleNamespace(get=AsyncMock(return_value=b"content"))
    detail = await service.detail(uuid4(), uuid4(), document.id)
    assert detail.size_bytes == 7 and detail.embedding_dimension == 384 and detail.chunk_count == 1
    assert "private-key" not in str(detail.model_dump())
    assert (await service.download(uuid4(), uuid4(), document.id))[2] == b"content"
    service.storage.get.assert_awaited_once_with("private-key")
