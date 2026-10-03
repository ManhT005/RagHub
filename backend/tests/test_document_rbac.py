import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.auth import OrganizationContext, get_organization_context
from app.core.database import get_session
from app.main import app
from app.modules.documents.schemas import DocumentAccepted
from app.modules.documents.service import DocumentService
from app.modules.memberships.models import MembershipRole


def test_unassigned_workspace_admin_cannot_upload_or_retry() -> None:
    async def context() -> OrganizationContext:
        class MembershipStub:
            role = "WORKSPACE_ADMIN"
            user_id = uuid.uuid4()

        return OrganizationContext(organization_id=uuid.uuid4(), membership=MembershipStub())  # type: ignore[arg-type]

    async def session():
        return SimpleNamespace(scalar=AsyncMock(return_value=None))

    app.dependency_overrides[get_organization_context] = context
    app.dependency_overrides[get_session] = session
    try:
        client = TestClient(app)
        workspace_id, version_id = uuid.uuid4(), uuid.uuid4()
        upload = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            files={"file": ("a.txt", b"hello", "text/plain")},
        )
        retry = client.post(
            f"/api/v1/workspaces/{workspace_id}/document-versions/{version_id}/retry"
        )
    finally:
        app.dependency_overrides.clear()
    assert upload.status_code == retry.status_code == 403
    assert upload.json()["error"]["code"] == "WORKSPACE_ACCESS_DENIED"
    assert retry.json()["error"]["code"] == "WORKSPACE_ACCESS_DENIED"


@pytest.mark.parametrize("role", [MembershipRole.ADMIN])
def test_writers_can_upload_and_retry(role, monkeypatch):
    organization_id, workspace_id, version_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    accepted = DocumentAccepted(
        document_id=uuid.uuid4(),
        document_version_id=version_id,
        job_id=uuid.uuid4(),
        status="QUEUED",
        created_at=datetime.now(UTC),
    )
    upload = AsyncMock(return_value=accepted)
    retry = AsyncMock(return_value=accepted)
    monkeypatch.setattr("app.modules.documents.router.upload_from_http", upload)
    monkeypatch.setattr(DocumentService, "retry", retry)

    async def context():
        return OrganizationContext(organization_id, SimpleNamespace(role=role))

    async def session():
        return None

    app.dependency_overrides[get_organization_context] = context
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/workspaces/{workspace_id}/documents",
                files={"file": ("a.txt", b"text", "text/plain")},
            )
            assert response.status_code == 202 and response.json()["status"] == "QUEUED"
            response = client.post(
                f"/api/v1/workspaces/{workspace_id}/document-versions/{version_id}/retry"
            )
            assert response.status_code == 202
        upload.assert_awaited_once()
        retry.assert_awaited_once_with(organization_id, workspace_id, version_id)
    finally:
        app.dependency_overrides.clear()


def test_assigned_workspace_admin_can_upload(monkeypatch):
    organization_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    accepted = DocumentAccepted(
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        status="QUEUED",
        created_at=datetime.now(UTC),
    )
    upload = AsyncMock(return_value=accepted)
    monkeypatch.setattr("app.modules.documents.router.upload_from_http", upload)

    user_id = uuid.uuid4()

    async def context():
        membership = SimpleNamespace(role="WORKSPACE_ADMIN", user_id=user_id)
        return OrganizationContext(organization_id, membership)

    class SessionStub:
        async def scalar(self, statement):
            return SimpleNamespace(user_id=user_id, workspace_id=workspace_id)

    async def session():
        return SessionStub()

    app.dependency_overrides[get_organization_context] = context
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/workspaces/{workspace_id}/documents",
                files={"file": ("a.txt", b"text", "text/plain")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    upload.assert_awaited_once()
