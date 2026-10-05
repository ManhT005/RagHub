from dataclasses import replace
from uuid import uuid4

import pytest

from raghub_core.api import (
    ChatbotConfig,
    ChatCompleted,
    ChatFailed,
    CitationsResolved,
    ConversationStarted,
    CoreError,
    RetrievalScope,
    RetrievedChunk,
    StreamChatCommand,
    StreamRagChatUseCase,
    TokenDelta,
    UsageReported,
)
from raghub_core.domain.providers.contracts import ChatMessage, ChatStreamDelta, ChatUsage
from raghub_core.domain.providers.errors import ProviderUnavailableError
from raghub_core.domain.rag.prompt import EMPTY_CONTEXT_ANSWER

from .fakes import FakeProviderResolver


class Chatbots:
    def __init__(self):
        self.config = ChatbotConfig(
            uuid4(), RetrievalScope(uuid4(), uuid4()), "Bot", "Be concise.", 5, True
        )

    async def get(self, organization_id, chatbot_id):
        return self.config


class Retrieval:
    def __init__(self):
        self.hits = [
            RetrievedChunk(
                uuid4(), uuid4(), uuid4(), "trusted knowledge", "guide.md", 4, "Guide", 0.03
            )
        ]
        self.calls = []

    async def retrieve(self, scope, question, limit):
        self.calls.append((scope, question, limit))
        return self.hits


class Conversations:
    def __init__(self):
        self.id = uuid4()
        self.messages = []
        self.commits = 0
        self.failures = []

    async def open(self, chatbot, conversation_id, external_user_id):
        return self.id

    async def add_user(self, conversation_id, content):
        self.messages.append(("user", content))
        return uuid4()

    async def history(self, conversation_id):
        return [ChatMessage(*message) for message in self.messages]

    async def add_assistant(self, conversation_id, content, usage, citations):
        self.messages.append(("assistant", content))
        self.usage, self.citations = usage, citations
        return uuid4()

    async def add_failed_assistant(self, conversation_id, content, error_code):
        self.failures.append((content, error_code))
        return uuid4()

    async def commit(self):
        self.commits += 1


class Usage:
    def __init__(self):
        self.records = []

    async def record_chat_usage(self, record):
        self.records.append(record)


def runtime():
    chatbots, retrieval, providers = Chatbots(), Retrieval(), FakeProviderResolver()
    conversations, usage = Conversations(), Usage()
    use_case = StreamRagChatUseCase(chatbots, retrieval, providers, conversations, usage)
    command = StreamChatCommand(
        chatbots.config.scope.organization_id, chatbots.config.id, "question"
    )
    return command, chatbots, retrieval, providers, conversations, usage, use_case


async def test_runtime_preserves_events_trusted_citations_native_usage_and_scope():
    command, chatbots, retrieval, providers, conversations, usage, use_case = runtime()
    providers.chat.deltas = [
        ChatStreamDelta(text="See [C99]"),
        ChatStreamDelta(usage=ChatUsage(10, 2, 12, "provider")),
    ]
    events = [event async for event in use_case.execute(command)]
    assert [type(event) for event in events] == [
        ConversationStarted,
        CitationsResolved,
        TokenDelta,
        UsageReported,
        ChatCompleted,
    ]
    assert events[1].citations == conversations.citations
    assert events[1].citations[0].citation_id == "C1"
    assert events[1].citations[0].chunk_id == retrieval.hits[0].chunk_id
    assert events[3].usage == ChatUsage(10, 2, 12, "provider")
    assert usage.records[0].scope == chatbots.config.scope
    assert providers.chat_scopes == [chatbots.config.scope]
    assert events[4].first_token_ms <= events[4].latency_ms
    assert conversations.commits == 2
    prompt = providers.chat.calls[0][0]
    assert "untrusted document context" in prompt[0].content
    assert "trusted knowledge" in prompt[0].content
    assert prompt[-1] == ChatMessage("user", command.question)


async def test_empty_context_skips_chat_resolution_and_usage_recording():
    command, _, retrieval, providers, conversations, usage, use_case = runtime()
    retrieval.hits = []
    events = [event async for event in use_case.execute(command)]
    assert not providers.chat_scopes and not providers.chat.calls and not usage.records
    assert events[1] == CitationsResolved(()) and events[2] == TokenDelta(EMPTY_CONTEXT_ANSWER)
    assert events[3].usage == ChatUsage(0, 0, 0, "none")
    assert events[4].first_token_ms is None and events[4].latency_ms == 0
    assert conversations.messages[-1] == ("assistant", EMPTY_CONTEXT_ANSWER)


async def test_runtime_estimates_missing_provider_usage():
    command, _, _, _, _, usage, use_case = runtime()
    events = [event async for event in use_case.execute(command)]
    assert events[3].usage.source == "estimated"
    assert events[3].usage.total_tokens > 0
    assert usage.records[0].usage == events[3].usage


async def test_current_question_is_appended_once_after_previous_history():
    command, _, _, providers, conversations, _, use_case = runtime()
    conversations.messages = [("user", "earlier"), ("assistant", "previous answer")]
    _ = [event async for event in use_case.execute(command)]
    prompt = providers.chat.calls[0][0]
    assert prompt[1:] == [
        ChatMessage("user", "earlier"),
        ChatMessage("assistant", "previous answer"),
        ChatMessage("user", command.question),
    ]


@pytest.mark.parametrize("failure", ["resolution", "retrieval", "timeout", "unexpected"])
async def test_failure_policy_saves_user_and_failed_assistant_before_error_event(failure):
    command, _, retrieval, providers, conversations, usage, use_case = runtime()
    if failure in {"resolution", "retrieval"}:

        async def fail(*_):
            assert conversations.commits == 1
            raise CoreError("PROVIDER_NOT_CONFIGURED", "The AI provider is not configured.")

        if failure == "resolution":
            providers.resolve_chat = fail
        else:
            retrieval.retrieve = fail
        code, partial = "PROVIDER_NOT_CONFIGURED", ""
    else:
        providers.chat.error = (
            TimeoutError() if failure == "timeout" else RuntimeError("vendor-secret")
        )
        code = "PROVIDER_TIMEOUT" if failure == "timeout" else "CHAT_RUNTIME_FAILED"
        partial = "answer"
    events = [event async for event in use_case.execute(command)]
    assert isinstance(events[0], ConversationStarted)
    assert isinstance(events[-1], ChatFailed) and events[-1].code == code
    assert conversations.messages == [("user", command.question)]
    assert conversations.failures == [(partial, code)] and conversations.commits == 2
    assert not usage.records and not any(isinstance(event, ChatCompleted) for event in events)
    assert "vendor-secret" not in repr(events)


async def test_provider_failure_after_token_never_retries_or_persists_completed_answer():
    command, _, _, providers, conversations, usage, use_case = runtime()
    providers.chat.error = ProviderUnavailableError()
    events = [event async for event in use_case.execute(command)]
    assert [type(event) for event in events] == [
        ConversationStarted,
        CitationsResolved,
        TokenDelta,
        ChatFailed,
    ]
    assert len(providers.chat.calls) == 1 and not usage.records and conversations.commits == 2
    assert conversations.messages == [("user", command.question)]
    assert conversations.failures == [("answer", "PROVIDER_UNAVAILABLE")]


@pytest.mark.parametrize("wrong_tenant", [False, True])
async def test_access_check_precedes_retrieval(wrong_tenant):
    command, chatbots, retrieval, providers, _, _, use_case = runtime()
    if wrong_tenant:
        command = replace(command, organization_id=uuid4())
    else:
        chatbots.config = replace(chatbots.config, published=False)
    with pytest.raises(CoreError) as error:
        _ = [event async for event in use_case.execute(command)]
    assert error.value.code == ("CHATBOT_NOT_FOUND" if wrong_tenant else "CHATBOT_NOT_PUBLISHED")
    assert not retrieval.calls and not providers.chat_scopes


async def test_closing_runtime_stream_closes_provider_and_leaves_no_completed_message():
    command, _, _, providers, conversations, usage, use_case = runtime()
    closed = []

    async def provider_stream(*_):
        try:
            yield ChatStreamDelta(text="partial")
            yield ChatStreamDelta(text="more")
        finally:
            closed.append(True)

    providers.chat.stream_chat = provider_stream
    stream = use_case.execute(command)
    assert isinstance(await anext(stream), ConversationStarted)
    assert isinstance(await anext(stream), CitationsResolved)
    assert isinstance(await anext(stream), TokenDelta)
    await stream.aclose()
    assert closed == [True] and not usage.records and conversations.commits == 1
    assert not conversations.failures
