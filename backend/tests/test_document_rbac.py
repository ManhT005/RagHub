import uuid

from fastapi.testclient import TestClient

from app.core.auth import OrganizationContext, get_organization_context
from app.core.database import get_session
from app.main import app
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
