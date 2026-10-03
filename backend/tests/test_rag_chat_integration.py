from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core_domain.rag.models import StreamChatCommand
from app.delivery.http.sse import event_payload
from app.modules.ai_providers.contracts import ChatStreamDelta, ChatUsage
from app.modules.chatbots.models import Message, MessageCitation, UsageEvent
from app.modules.chatbots.service import ChatbotService


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
async def test_successful_rag_stream_persists_usage_and_selected_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    workspace_id = uuid4()
    chatbot = SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_id,
        published=True,
        retrieval_limit=5,
        system_prompt="Be concise.",
        model=None,
    )
    conversation = SimpleNamespace(id=uuid4())
    selected_hit = {
        "document_id": str(uuid4()),
        "document_version_id": str(uuid4()),
        "chunk_id": str(uuid4()),
        "source_name": "guide.pdf",
        "page_number": 4,
        "heading": "Admissions",
        "content": "Applications close on 30 June.",
        "score": 0.032,
    }

    class Service(ChatbotService):
        async def get(self, organization_id: object, chatbot_id: object) -> object:
            return chatbot

        async def _conversation(self, *args: object) -> object:
            return conversation

        async def _history(self, conversation_id: object) -> list[dict[str, str]]:
            return [{"role": "user", "content": "When is the deadline?"}]

    class Search:
        def __init__(self, session: object) -> None:
            pass

        async def retrieve(self, *args: object) -> list[dict[str, object]]:
            return [selected_hit]

    class Provider:
        async def stream_chat(self, messages: object, options: object):
            yield ChatStreamDelta(text="30 June")
            yield ChatStreamDelta(usage=ChatUsage(42, 2, 44, "provider"))

    class Resolver:
        def __init__(self, session: object) -> None:
            pass

        async def chat_for_workspace(self, *args: object) -> object:
            return SimpleNamespace(
                provider=Provider(),
                config=SimpleNamespace(provider_type="OPENAI_COMPATIBLE", model="chat-model"),
            )

    import app.modules.chatbots.service as service_module

    monkeypatch.setattr(service_module, "SearchService", Search)
    monkeypatch.setattr(service_module, "ProviderResolver", Resolver)
    session = SessionStub()

    events = [
        event_payload(event)
        async for event in Service(session).stream_events(
            StreamChatCommand(organization_id, chatbot.id, "deadline", None, "user")
        )
    ]

    assert [name for name, _ in events] == [
        "conversation",
        "citations",
        "token",
        "usage",
        "done",
    ]
    assert events[1][1]["citations"][0]["citation_id"] == "C1"  # type: ignore[index]
    assert events[3][1] == {
        "prompt_tokens": 42,
        "completion_tokens": 2,
        "total_tokens": 44,
        "source": "provider",
    }
    assert events[4][1]["first_token_ms"] <= events[4][1]["latency_ms"]  # type: ignore[operator]

    assistant = next(
        value for value in session.added if isinstance(value, Message) and value.role == "assistant"
    )
    usage_event = next(value for value in session.added if isinstance(value, UsageEvent))
    citation = next(value for value in session.added if isinstance(value, MessageCitation))
    assert assistant.content == "30 June"
    assert assistant.usage_json == events[3][1]
    assert (usage_event.prompt_tokens, usage_event.completion_tokens) == (42, 2)
    assert usage_event.first_token_ms is not None
    assert str(citation.chunk_id) == selected_hit["chunk_id"]
