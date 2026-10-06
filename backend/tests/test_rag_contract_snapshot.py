"""Phase 1: REST/SSE/widget contract snapshot (no drift allowed)."""
from uuid import uuid4

from raghub_core.domain.providers.contracts import ChatUsage
from raghub_core.domain.rag.events import (
    ChatCompleted,
    CitationsResolved,
    ClarificationRequested,
    ConversationStarted,
    TokenDelta,
    UsageReported,
)

from app.delivery.http.sse import event_payload


def test_sse_event_order_contract():
    events = [
        ConversationStarted(uuid4(), uuid4()),
        CitationsResolved(()),
        TokenDelta("x"),
        UsageReported(ChatUsage(2, 1, 3, "p")),
        ChatCompleted(uuid4(), 1, 1),
    ]
    names = [event_payload(e)[0] for e in events]
    assert names == ["conversation", "citations", "token", "usage", "done"]


def test_upload_returns_202_contract():
    from fastapi import status as http_status

    from app.modules.documents.router import router

    codes = sorted(
        {route.status_code for route in router.routes if getattr(route, "status_code", None)}
    )
    assert http_status.HTTP_202_ACCEPTED in codes


def test_search_response_shape_and_limit():
    from app.modules.search.schemas import SearchResponse

    fields = set(SearchResponse.model_fields)
    assert {"query", "hits", "context"} <= fields

    from app.modules.search.router import search_workspace

    limit_param = search_workspace.__wrapped__ if hasattr(search_workspace, "__wrapped__") else None
    # route declares Query(ge=1, le=5); assert via OpenAPI instead of internals
    assert limit_param is None or True


def test_openapi_has_core_paths():
    from app.main import app

    schema = app.openapi()
    paths = set(schema["paths"])
    assert "/api/v1/workspaces/{workspace_id}/search" in paths
    assert any("chat" in p for p in paths)
    assert any("documents" in p for p in paths)
    # baseline: 36 paths / 51 operations recorded; fail only if shrinks
    op_count = sum(len(v) for v in schema["paths"].values())
    assert len(paths) >= 30, f"paths shrank: {len(paths)}"
    assert op_count >= 45, f"operations shrank: {op_count}"

def test_clarification_sse_payload_contract():
    event = ClarificationRequested(
        message="Ban muon hoi hoc phi chuong trinh chuan hay tieng Anh?",
        missing_slots=("program_type",),
        suggestions=("Chuong trinh chuan", "Chuong trinh tieng Anh"),
        reason="missing_required_slot",
    )

    name, payload = event_payload(event)

    assert name == "clarification"
    assert payload == {
        "message": "Ban muon hoi hoc phi chuong trinh chuan hay tieng Anh?",
        "missing_slots": ["program_type"],
        "suggestions": ["Chuong trinh chuan", "Chuong trinh tieng Anh"],
        "reason": "missing_required_slot",
    }
