import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import asdict

from app.core_domain.errors import CoreError
from app.core_domain.rag.events import (
    ChatCompleted,
    ChatFailed,
    CitationsResolved,
    ConversationStarted,
    RagEvent,
    TokenDelta,
    UsageReported,
)


def event_payload(event: RagEvent) -> tuple[str, dict[str, object]]:
    if isinstance(event, ConversationStarted):
        return "conversation", {
            "conversation_id": str(event.conversation_id),
            "user_message_id": str(event.user_message_id),
        }
    if isinstance(event, CitationsResolved):
        return "citations", {"citations": [citation.as_payload() for citation in event.citations]}
    if isinstance(event, TokenDelta):
        return "token", {"text": event.text}
    if isinstance(event, UsageReported):
        return "usage", asdict(event.usage)
    if isinstance(event, ChatCompleted):
        return "done", {
            "message_id": str(event.message_id),
            "first_token_ms": event.first_token_ms,
            "latency_ms": event.latency_ms,
        }
    if isinstance(event, ChatFailed):
        return "error", {"code": event.code, "message": event.message}
    raise TypeError(f"Unsupported RAG event: {type(event).__name__}")


def serialize_event(event: RagEvent) -> str:
    name, data = event_payload(event)
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_sse(events: AsyncIterator[RagEvent]) -> AsyncIterator[str]:
    try:
        async with aclosing(events) as stream:
            async for event in stream:
                yield serialize_event(event)
    except CoreError as exc:
        yield serialize_event(ChatFailed(exc.code, exc.message))
