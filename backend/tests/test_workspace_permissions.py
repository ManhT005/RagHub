from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import (
    OrganizationContext,
    get_organization_context,
    require_workspace_permission,
)
from app.core.database import get_session
from app.core.exceptions import AppError
from app.main import app
from app.modules.documents.service import DocumentService
from app.modules.workspace_access.permissions import PERMISSIONS, normalize_permissions


def test_dependencies_and_unknown_system_permission():
    assert normalize_permissions(["document.upload", "ai.change_embedding", "member.manage"]) == [
        "workspace.view",
        "document.view",
        "document.upload",
        "ai.view",
        "ai.change_embedding",
        "member.view",
        "member.manage",
    ]
    with pytest.raises(AppError):
        normalize_permissions(["system.admin"])


async def test_admin_bypass_is_still_scoped_and_disabled_members_are_denied():
    context = OrganizationContext(uuid4(), SimpleNamespace(role="ADMIN", status="ACTIVE"))
    session = SimpleNamespace(scalar=AsyncMock(return_value=uuid4()))
    await require_workspace_permission(context, uuid4(), "document.delete", session)
    statement = str(session.scalar.call_args.args[0])
    assert "organization_id" in statement and "deleted_at IS NULL" in statement
    session.scalar.return_value = None
    with pytest.raises(AppError) as denied:
        await require_workspace_permission(context, uuid4(), "document.delete", session)
    assert denied.value.status_code == 403
    context.membership.status = "DISABLED"
    with pytest.raises(AppError):
        await require_workspace_permission(context, uuid4(), "document.delete", session)


def test_read_only_member_cannot_mutate_even_with_direct_http_requests(monkeypatch):
    organization_id, workspace_id, user_id = uuid4(), uuid4(), uuid4()
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=workspace_id),
        scalars=AsyncMock(return_value=["workspace.view", "document.view"]),
    )
    context = OrganizationContext(
        organization_id,
        SimpleNamespace(
            role="WORKSPACE_ADMIN",
            user_id=user_id,
            status="ACTIVE",
        ),
    )
    app.dependency_overrides[get_organization_context] = lambda: context
    app.dependency_overrides[get_session] = lambda: session
    monkeypatch.setattr(DocumentService, "list_documents", AsyncMock(return_value=[]))
    try:
        with TestClient(app) as client:
            assert client.get(f"/api/v1/workspaces/{workspace_id}/documents").status_code == 200
            paths = [
                ("delete", f"documents/{uuid4()}"),
                ("post", f"document-versions/{uuid4()}/reindex"),
                ("post", f"document-versions/{uuid4()}/retry"),
            ]
            for method, path in paths:
                response = client.request(method, f"/api/v1/workspaces/{workspace_id}/{path}")
                assert response.status_code == 403
                assert response.json()["error"]["code"] == "WORKSPACE_PERMISSION_DENIED"
            response = client.post(
                f"/api/v1/workspaces/{workspace_id}/documents",
                files={"file": ("a.txt", b"hello", "text/plain")},
            )
            assert response.status_code == 403
            assert client.get(f"/api/v1/workspaces/{workspace_id}/members").status_code == 403
            response = client.get(f"/api/v1/organizations/{organization_id}/providers")
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_backfill_permission_set_is_frozen():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[1] / "alembic/versions/20261004_0013_workspace_permissions.py"
    spec = importlib.util.spec_from_file_location("permissions_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.PERMISSIONS == PERMISSIONS
