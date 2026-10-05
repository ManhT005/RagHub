from types import SimpleNamespace
from uuid import uuid4

import pytest
from raghub_core.domain.rag.models import StreamChatCommand

from app.delivery.http.sse import event_payload
from app.modules.chatbots.service import EMPTY_CONTEXT_ANSWER, ChatbotService


class SessionStub:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    async def commit(self) -> None:
        await self.flush()


@pytest.mark.asyncio
async def test_empty_context_skips_chat_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    organization_id = uuid4()
    workspace_id = uuid4()
    conversation_id = uuid4()
    chatbot = SimpleNamespace(
        id=uuid4(), workspace_id=workspace_id, published=True, retrieval_limit=5
    )

    class Service(ChatbotService):
        async def _history(self, conversation_id):
            return []

        async def get(self, organization_id: object, chatbot_id: object) -> object:
            return chatbot

        async def _conversation(self, *args: object) -> object:
            return SimpleNamespace(id=conversation_id)

    class EmptySearch:
        def __init__(self, session: object) -> None:
            pass

        async def retrieve(self, *args: object) -> list[dict[str, object]]:
            return []

    class ForbiddenResolver:
        def __init__(self, session: object) -> None:
            raise AssertionError("chat provider must not be resolved for empty context")

    import app.composition.self_host as composition
    from app.infrastructure.chat_runtime import RuntimeRetrievalAdapter

    monkeypatch.setattr(
        composition.SelfHostContainer,
        "retrieve_context",
        lambda self: RuntimeRetrievalAdapter(lambda: EmptySearch(None)),
    )
    monkeypatch.setattr(composition, "ProviderResolver", ForbiddenResolver)
    session = SessionStub()

    events = [
        event_payload(event)
        async for event in Service(session).stream_events(
            StreamChatCommand(organization_id, chatbot.id, "unknown", None, "user")
        )
    ]

    assert [name for name, _ in events] == [
        "conversation",
        "citations",
        "token",
        "usage",
        "done",
    ]
    assert events[1][1] == {"citations": []}
    assert events[2][1] == {"text": EMPTY_CONTEXT_ANSWER}
    assert events[3][1] == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "source": "none",
    }
    assert not any(type(value).__name__ == "UsageEvent" for value in session.added)
