from uuid import UUID

from fastapi.testclient import TestClient

from app.core.auth import OrganizationContext, get_organization_context
from app.main import app
from app.modules.memberships.models import MembershipRole

client = TestClient(app)


def test_liveness_returns_request_id() -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "test-request"


def test_validation_errors_use_standard_envelope() -> None:
    class MembershipStub:
        role = MembershipRole.VIEWER

    async def organization_context_override() -> OrganizationContext:
        return OrganizationContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            membership=MembershipStub(),  # type: ignore[arg-type]
        )

    app.dependency_overrides[get_organization_context] = organization_context_override
    try:
        response = client.get("/api/v1/workspaces/not-a-uuid/search", params={"q": "hello"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    payload = response.json()["error"]
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["request_id"]
    assert payload["details"]["errors"]
