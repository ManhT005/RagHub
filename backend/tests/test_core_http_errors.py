import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from raghub_core.domain.errors import CoreError

from app.core.exceptions import register_exception_handlers
from app.delivery.http.error_mapping import AppError, http_status


@pytest.mark.parametrize(
    "code,status",
    [
        ("CHATBOT_NOT_FOUND", 404),
        ("CHATBOT_NOT_PUBLISHED", 409),
        ("CONVERSATION_ACCESS_DENIED", 403),
        ("SEARCH_UNAVAILABLE", 503),
        ("PROVIDER_TIMEOUT", 504),
        ("PROVIDER_NOT_CONFIGURED", 422),
        ("FILE_TOO_LARGE", 413),
        ("INVALID_CHATBOT_CONFIG", 400),
        ("UNKNOWN_CORE_ERROR", 500),
    ],
)
def test_core_error_mapping_at_http_boundary_preserves_envelope(code, status):
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/failure")
    async def failure():
        raise CoreError(code, "Operation failed.", details={"reason": "test"})

    response = TestClient(app).get("/failure")
    assert response.status_code == status
    assert response.json() == {
        "error": {
            "code": code,
            "message": "Operation failed.",
            "details": {"reason": "test"},
            "request_id": "unknown",
        }
    }


def test_legacy_http_error_keeps_explicit_status_override():
    assert http_status(AppError("CUSTOM", "test", status_code=418)) == 418
