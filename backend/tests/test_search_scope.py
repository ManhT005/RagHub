from uuid import UUID

from fastapi.testclient import TestClient

from app.core.auth import OrganizationContext, get_organization_context
from app.main import app
from app.modules.memberships.models import MembershipRole


class FakeSearchService:
    captured: dict[str, object] = {}

    def __init__(self, _session: object) -> None:
        pass

    async def retrieve(
        self, organization_id: UUID, workspace_id: UUID, query: str, limit: int
    ) -> list[dict[str, object]]:
        self.captured.update(
            organization_id=organization_id,
            workspace_id=workspace_id,
            query=query,
            limit=limit,
        )
        return []


def test_search_passes_both_tenant_filters(monkeypatch: object) -> None:
    import app.modules.search.router as search_router

    monkeypatch.setattr(search_router, "SearchService", FakeSearchService)  # type: ignore[attr-defined]
    client = TestClient(app)
    organization_id = UUID("00000000-0000-0000-0000-000000000001")
    workspace_id = UUID("00000000-0000-0000-0000-000000000002")

    class MembershipStub:
        role = MembershipRole.VIEWER

    async def organization_context_override() -> OrganizationContext:
        return OrganizationContext(organization_id=organization_id, membership=MembershipStub())  # type: ignore[arg-type]

    app.dependency_overrides[get_organization_context] = organization_context_override

    try:
        response = client.get(
            f"/api/v1/workspaces/{workspace_id}/search", params={"q": "graduation"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert FakeSearchService.captured["organization_id"] == organization_id
    assert FakeSearchService.captured["workspace_id"] == workspace_id
