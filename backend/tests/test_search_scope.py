from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app


class FakeChunkSearch:
    captured: dict[str, object] = {}

    async def search(self, **kwargs: object) -> list[dict[str, object]]:
        self.captured.update(kwargs)
        return []

    async def close(self) -> None:
        return None


def test_search_passes_both_tenant_filters(monkeypatch: object) -> None:
    import app.modules.search.router as search_router

    monkeypatch.setattr(search_router, "ChunkSearch", FakeChunkSearch)  # type: ignore[attr-defined]
    client = TestClient(app)
    organization_id = UUID("00000000-0000-0000-0000-000000000001")
    workspace_id = UUID("00000000-0000-0000-0000-000000000002")

    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/search",
        params={"q": "graduation"},
        headers={"X-Organization-ID": str(organization_id)},
    )

    assert response.status_code == 200
    assert FakeChunkSearch.captured["organization_id"] == organization_id
    assert FakeChunkSearch.captured["workspace_id"] == workspace_id
