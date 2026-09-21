from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_liveness_returns_request_id() -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "test-request"


def test_validation_errors_use_standard_envelope() -> None:
    response = client.get(
        "/api/v1/workspaces/not-a-uuid/search",
        params={"q": "hello"},
        headers={"X-Organization-ID": "also-not-a-uuid"},
    )

    assert response.status_code == 422
    payload = response.json()["error"]
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["request_id"]
    assert payload["details"]["errors"]
