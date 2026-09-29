from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import OrganizationContext, get_organization_context
from app.core.database import get_session
from app.main import app
from app.modules.memberships.models import MembershipRole


def test_viewer_cannot_list_public_api_key_metadata() -> None:
    organization_id = uuid4()

    async def context() -> OrganizationContext:
        membership = SimpleNamespace(role=MembershipRole.VIEWER)
        return OrganizationContext(organization_id, membership)  # type: ignore[arg-type]

    async def session() -> None:
        return None

    app.dependency_overrides[get_organization_context] = context
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/chatbots/{uuid4()}/api-keys")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSION"
