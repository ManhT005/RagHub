import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from raghub_core.api import (
    ChatbotConfig,
    ChatCompleted,
    ChatFailed,
    CitationsResolved,
    ClarificationRequested,
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
from raghub_core.domain.rag.intent import IntentAction, IntentDecision
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


class FakeClarificationPolicy:
    def is_clarification(self, text):
        return text.startswith("Please clarify ")

    def evaluate(self, question, *, mode, clarifying_turns, max_clarifying_turns, **kwargs):
        if mode == "off" or clarifying_turns >= max_clarifying_turns:
            return IntentDecision(IntentAction.ANSWER_NOW)
        if question == "ignore instructions":
            return IntentDecision(
                IntentAction.REFUSE_OR_REDIRECT, message="Use the provided documents."
            )
        if question == "ambiguous?" or (question == "topic" and mode == "proactive"):
            slots = ("scope",) if question == "ambiguous?" else ("topic",)
            return IntentDecision(
                IntentAction.CLARIFY, missing_slots=slots, message="Please clarify scope."
            )
        return IntentDecision(IntentAction.ANSWER_NOW)


def runtime():
    chatbots, retrieval, providers = Chatbots(), Retrieval(), FakeProviderResolver()
    conversations, usage = Conversations(), Usage()
    use_case = StreamRagChatUseCase(
        chatbots,
        retrieval,
        providers,
        conversations,
        usage,
        clarification_policy=FakeClarificationPolicy(),
    )
    command = StreamChatCommand(
        chatbots.config.scope.organization_id, chatbots.config.id, "question"
    )
    return command, chatbots, retrieval, providers, conversations, usage, use_case


def test_post_retrieval_clarification_uses_confidence_without_generating():
    from raghub_core.domain.retrieval.models import RetrievalAssessment

    command, _, retrieval, providers, conversations, _, use_case = runtime()

    class ConfidencePolicy(FakeClarificationPolicy):
        def evaluate(self, question, **kwargs):
            if kwargs.get("retrieval_confidence") == 0.6:
                return IntentDecision(IntentAction.CLARIFY, message="Please clarify scope.")
            return IntentDecision(IntentAction.ANSWER_NOW)

    async def assess(*args):
        return RetrievalAssessment(tuple(retrieval.hits), 0.6)

    use_case.clarification_policy = ConfidencePolicy()
    use_case.retrieval_assessor = assess
    events = asyncio.run(_collect_events(use_case, command))
    assert any(isinstance(event, ClarificationRequested) for event in events)
    assert conversations.messages[-1] == ("assistant", "Please clarify scope.")
    assert providers.chat_scopes == []


async def _collect_events(use_case, command):
    return [event async for event in use_case.execute(command)]


async def _close_after_first_token(use_case, command) -> None:
    stream = use_case.execute(command)
    assert isinstance(await anext(stream), ConversationStarted)
    assert isinstance(await anext(stream), CitationsResolved)
    assert isinstance(await anext(stream), TokenDelta)
    await stream.aclose()


def test_runtime_preserves_events_trusted_citations_native_usage_and_scope():
    command, chatbots, retrieval, providers, conversations, usage, use_case = runtime()
    providers.chat.deltas = [
        ChatStreamDelta(text="See [C99]"),
        ChatStreamDelta(usage=ChatUsage(10, 2, 12, "provider")),
    ]
    events = asyncio.run(_collect_events(use_case, command))
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


def test_empty_context_skips_chat_resolution_and_usage_recording():
    command, _, retrieval, providers, conversations, usage, use_case = runtime()
    retrieval.hits = []
    events = asyncio.run(_collect_events(use_case, command))
    assert not providers.chat_scopes and not providers.chat.calls and not usage.records
    assert events[1] == CitationsResolved(()) and events[2] == TokenDelta(EMPTY_CONTEXT_ANSWER)
    assert events[3].usage == ChatUsage(0, 0, 0, "none")
    assert events[4].first_token_ms is None and events[4].latency_ms == 0
    assert conversations.messages[-1] == ("assistant", EMPTY_CONTEXT_ANSWER)


def test_ambiguous_question_emits_clarification_without_retrieval_or_provider():
    command, _, retrieval, providers, conversations, usage, use_case = runtime()
    command = replace(command, question="ambiguous?")

    events = asyncio.run(_collect_events(use_case, command))

    assert [type(event) for event in events] == [
        ConversationStarted,
        ClarificationRequested,
        UsageReported,
        ChatCompleted,
    ]
    assert not retrieval.calls and not providers.chat_scopes and not providers.chat.calls
    assert not usage.records
    assert events[1].missing_slots == ("scope",)
    assert events[2].usage == ChatUsage(0, 0, 0, "none")
    assert events[3].first_token_ms is None and events[3].latency_ms == 0
    assert conversations.messages[-1] == ("assistant", events[1].message)
    assert conversations.commits == 2


def test_clarification_limit_falls_back_to_retrieval_answer_path():
    command, _, retrieval, providers, conversations, _, use_case = runtime()
    conversations.messages = [
        ("assistant", "Please clarify scope."),
    ]
    command = replace(command, question="ambiguous?")

    events = asyncio.run(_collect_events(use_case, command))

    assert [type(event) for event in events] == [
        ConversationStarted,
        CitationsResolved,
        TokenDelta,
        UsageReported,
        ChatCompleted,
    ]
    assert retrieval.calls
    assert providers.chat_scopes
    assert not any(isinstance(event, ClarificationRequested) for event in events)


def test_legacy_ascii_clarification_prefix_still_counts_toward_limit() -> None:
    command, _, retrieval, providers, conversations, _, use_case = runtime()
    conversations.messages = [
        ("assistant", "Please clarify scope."),
    ]
    command = replace(command, question="ambiguous?")

    events = asyncio.run(_collect_events(use_case, command))

    assert [type(event) for event in events] == [
        ConversationStarted,
        CitationsResolved,
        TokenDelta,
        UsageReported,
        ChatCompleted,
    ]
    assert retrieval.calls
    assert providers.chat_scopes
    assert not any(isinstance(event, ClarificationRequested) for event in events)


def test_followup_after_clarification_uses_resolved_question_for_retrieval_and_prompt():
    command, _, retrieval, providers, conversations, _, use_case = runtime()
    first = replace(command, question="ambiguous?")
    first_events = asyncio.run(_collect_events(use_case, first))
    assert isinstance(first_events[1], ClarificationRequested)

    followup = replace(command, question="scope A")
    followup_events = asyncio.run(_collect_events(use_case, followup))

    assert [type(event) for event in followup_events] == [
        ConversationStarted,
        CitationsResolved,
        TokenDelta,
        UsageReported,
        ChatCompleted,
    ]
    assert retrieval.calls[-1][1] == "ambiguous? scope A"
    prompt = providers.chat.calls[-1][0]
    assert prompt[-1] == ChatMessage("user", "ambiguous? scope A")
    assert conversations.messages[-2:] == [
        ("user", "scope A"),
        ("assistant", "answer"),
    ]


def test_refuse_or_redirect_keeps_legacy_visible_token_stream():
    command, _, retrieval, providers, conversations, usage, use_case = runtime()
    command = replace(command, question="ignore instructions")

    events = asyncio.run(_collect_events(use_case, command))

    assert [type(event) for event in events] == [
        ConversationStarted,
        CitationsResolved,
        TokenDelta,
        UsageReported,
        ChatCompleted,
    ]
    assert not retrieval.calls and not providers.chat_scopes and not providers.chat.calls
    assert not usage.records
    assert events[1] == CitationsResolved(())
    assert events[2].text == "Use the provided documents."
    assert events[3].usage == ChatUsage(0, 0, 0, "none")
    assert conversations.messages[-1] == ("assistant", events[2].text)


def test_chatbot_off_mode_uses_legacy_answer_path_for_ambiguous_question():
    command, chatbots, retrieval, providers, _, _, use_case = runtime()
    chatbots.config = replace(chatbots.config, clarification_mode="off")
    command = replace(command, question="ambiguous?")

    events = asyncio.run(_collect_events(use_case, command))

    assert [type(event) for event in events] == [
        ConversationStarted,
        CitationsResolved,
        TokenDelta,
        UsageReported,
        ChatCompleted,
    ]
    assert retrieval.calls and providers.chat_scopes
    assert not any(isinstance(event, ClarificationRequested) for event in events)


def test_chatbot_proactive_mode_clarifies_short_topic_query():
    command, chatbots, retrieval, providers, _, _, use_case = runtime()
    chatbots.config = replace(chatbots.config, clarification_mode="proactive")
    command = replace(command, question="topic")

    events = asyncio.run(_collect_events(use_case, command))

    assert [type(event) for event in events] == [
        ConversationStarted,
        ClarificationRequested,
        UsageReported,
        ChatCompleted,
    ]
    assert events[1].missing_slots == ("topic",)
    assert not retrieval.calls and not providers.chat_scopes


def test_chatbot_conservative_mode_answers_short_topic_query():
    command, chatbots, retrieval, providers, _, _, use_case = runtime()
    chatbots.config = replace(chatbots.config, clarification_mode="conservative")
    command = replace(command, question="topic")

    events = asyncio.run(_collect_events(use_case, command))

    assert [type(event) for event in events] == [
        ConversationStarted,
        CitationsResolved,
        TokenDelta,
        UsageReported,
        ChatCompleted,
    ]
    assert retrieval.calls and providers.chat_scopes


def test_runtime_estimates_missing_provider_usage():
    command, _, _, _, _, usage, use_case = runtime()
    events = asyncio.run(_collect_events(use_case, command))
    assert events[3].usage.source == "estimated"
    assert events[3].usage.total_tokens > 0
    assert usage.records[0].usage == events[3].usage


def test_current_question_is_appended_once_after_previous_history():
    command, _, _, providers, conversations, _, use_case = runtime()
    conversations.messages = [("user", "earlier"), ("assistant", "previous answer")]
    _ = asyncio.run(_collect_events(use_case, command))
    prompt = providers.chat.calls[0][0]
    assert prompt[1:] == [
        ChatMessage("user", "earlier"),
        ChatMessage("assistant", "previous answer"),
        ChatMessage("user", command.question),
    ]


@pytest.mark.parametrize("failure", ["resolution", "retrieval", "timeout", "unexpected"])
def test_failure_policy_saves_user_and_failed_assistant_before_error_event(failure):
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
    events = asyncio.run(_collect_events(use_case, command))
    assert isinstance(events[0], ConversationStarted)
    assert isinstance(events[-1], ChatFailed) and events[-1].code == code
    assert conversations.messages == [("user", command.question)]
    assert conversations.failures == [(partial, code)] and conversations.commits == 2
    assert not usage.records and not any(isinstance(event, ChatCompleted) for event in events)
    assert "vendor-secret" not in repr(events)


def test_provider_failure_after_token_never_retries_or_persists_completed_answer():
    command, _, _, providers, conversations, usage, use_case = runtime()
    providers.chat.error = ProviderUnavailableError()
    events = asyncio.run(_collect_events(use_case, command))
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
def test_access_check_precedes_retrieval(wrong_tenant):
    command, chatbots, retrieval, providers, _, _, use_case = runtime()
    if wrong_tenant:
        command = replace(command, organization_id=uuid4())
    else:
        chatbots.config = replace(chatbots.config, published=False)
    with pytest.raises(CoreError) as error:
        _ = asyncio.run(_collect_events(use_case, command))
    assert error.value.code == ("CHATBOT_NOT_FOUND" if wrong_tenant else "CHATBOT_NOT_PUBLISHED")
    assert not retrieval.calls and not providers.chat_scopes


def test_closing_runtime_stream_closes_provider_and_leaves_no_completed_message():
    command, _, _, providers, conversations, usage, use_case = runtime()
    closed = []

    async def provider_stream(*_):
        try:
            yield ChatStreamDelta(text="partial")
            yield ChatStreamDelta(text="more")
        finally:
            closed.append(True)

    providers.chat.stream_chat = provider_stream
    asyncio.run(_close_after_first_token(use_case, command))
    assert closed == [True] and not usage.records and conversations.commits == 1
    assert not conversations.failures
