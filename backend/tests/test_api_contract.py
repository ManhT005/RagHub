"""API contract tests: envelopes, facade, upload/search shapes, artifact drift."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi import Request

REPO = Path(__file__).parent.parent.parent


def _tracked_openapi() -> dict:
    return json.loads((REPO / "docs" / "api" / "openapi.json").read_text(encoding="utf-8"))


def test_tracked_openapi_matches_runtime():
    from app.main import app

    live = app.openapi()
    tracked = _tracked_openapi()
    assert set(tracked["paths"]) == set(live["paths"])
    for path, ops in live["paths"].items():
        assert set(tracked["paths"][path]) == set(ops), path
    assert len(tracked["paths"]) == 65


def test_postman_collection_matches_openapi_operations():
    openapi = _tracked_openapi()
    collection = json.loads(
        (REPO / "postman" / "collections" / "raghub-api.postman_collection.json").read_text(
            encoding="utf-8"
        )
    )
    assert collection["info"]["schema"].endswith("/collection/v3/collection.json")
    op_count = sum(
        len([m for m in ops if m in {"get", "post", "patch", "put", "delete"}])
        for ops in openapi["paths"].values()
    )
    names = {item["name"] for item in collection["item"]}
    assert len(collection["item"]) >= op_count - 1
    assert "POST /api/v1/workspaces/{workspace_id}/documents" in names
    assert "GET /api/v1/workspaces/{workspace_id}/search" in names
    assert "POST /api/v1/chatbots/{chatbot_id}/chat" in names


def test_local_environment_has_placeholders_only():
    env = json.loads(
        (REPO / "postman" / "environments" / "local.example.json").read_text(encoding="utf-8")
    )
    for entry in env["values"]:
        value = entry["value"]
        assert (
            "REPLACE_WITH" in value
            or value.startswith("http://localhost")
            or entry["key"] == "search_query"
        ), entry["key"]


async def test_error_envelope_shape():
    from app.core.exceptions import _error_response

    scope = {"type": "http", "headers": [], "method": "GET", "path": "/",
             "query_string": b""}
    request = Request(scope)
    request.state.request_id = "req-1"
    response = _error_response(request, status_code=404, code="NOT_FOUND", message="Missing.")
    body = json.loads(response.body.decode())
    assert set(body["error"]) == {"code", "message", "request_id", "details"}
    assert body["error"]["code"] == "NOT_FOUND" and body["error"]["request_id"] == "req-1"


def test_upload_accept_and_search_limit_contract():
    from fastapi import status as http_status

    from app.modules.documents.router import router as documents_router
    from app.modules.documents.schemas import DocumentAccepted
    from app.modules.search.router import router as search_router

    assert http_status.HTTP_202_ACCEPTED in {
        route.status_code for route in documents_router.routes
        if getattr(route, "status_code", None)
    }
    assert set(DocumentAccepted.model_fields) == {
        "document_id", "document_version_id", "job_id", "status", "created_at",
    }
    search_paths = {getattr(route, "path", "") for route in search_router.routes}
    assert "/workspaces/{workspace_id}/search" in search_paths


def test_provider_facade_keeps_secret_semantics():
    from app.modules.ai_providers.schemas import ProviderConfigResponse

    assert ProviderConfigResponse.model_fields["has_secret"].annotation is bool
    assert "encrypted_secret" not in ProviderConfigResponse.model_fields
    assert "secret" not in ProviderConfigResponse.model_fields


def test_sse_terminal_semantics():
    from raghub_core.domain.rag.events import ChatCompleted, ChatFailed

    from app.delivery.http.sse import serialize_event

    done = serialize_event(ChatCompleted(uuid4(), 5, 50))
    error = serialize_event(ChatFailed("PROVIDER_TIMEOUT", "timed out"))
    assert done.startswith("event: done") and error.startswith("event: error")
    assert "PROVIDER_TIMEOUT" in error
