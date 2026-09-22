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


def test_viewer_cannot_upload_or_retry() -> None:
    async def context() -> OrganizationContext:
        class MembershipStub:
            role = MembershipRole.VIEWER

        return OrganizationContext(organization_id=uuid.uuid4(), membership=MembershipStub())  # type: ignore[arg-type]

    async def session() -> None:
        return None

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
    assert upload.json()["error"]["code"] == "INSUFFICIENT_PERMISSION"
    assert retry.json()["error"]["code"] == "INSUFFICIENT_PERMISSION"


@pytest.mark.parametrize(
    "role", [MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR]
)
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
    monkeypatch.setattr(DocumentService, "upload_document", upload)
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
