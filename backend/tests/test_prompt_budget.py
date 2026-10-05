"""Global prompt budget and citation validation (offline)."""
from uuid import uuid4

import pytest
from raghub_core.domain.errors import CoreError
from raghub_core.domain.providers.contracts import ChatMessage
from raghub_core.domain.rag.citation_validator import validate_citations
from raghub_core.domain.rag.citations import (
    render_sliced_bundle,
    resolve_sliced_citations,
)
from raghub_core.domain.rag.model_profile import (
    count_tokens_exact,
    count_tokens_fallback,
    resolve_profile,
    validate_budget_config,
)
from raghub_core.domain.rag.prompt_budget import PromptBudgeter
from raghub_core.domain.retrieval.models import RetrievedChunk


def _hit(content: str) -> RetrievedChunk:
    uid = uuid4()
    return RetrievedChunk(uid, uuid4(), uid, content, "src.md", 2, "H", 0.5)


def test_model_registry_known_and_fallback():
    assert resolve_profile("gemini-2.5-flash").profile.context_window == 1_048_576
    assert resolve_profile("gemini-2.5-flash").fallback_used is False
    unknown = resolve_profile("some-local-model")
    assert unknown.fallback_used is True and unknown.profile.context_window == 8_192
    assert count_tokens_exact("hello world") > 0
    assert count_tokens_fallback("x" * 400) >= 100


def test_budget_config_fails_fast():
    assert (
        validate_budget_config(context_window=8192, max_output_tokens=1024, safety_margin=256)
        == 6912
    )
    with pytest.raises(ValueError):
        validate_budget_config(context_window=1000, max_output_tokens=1024, safety_margin=256)


def test_system_plus_question_over_budget_errors_without_silent_cut():
    budgeter = PromptBudgeter(context_window=100, max_output_tokens=10, safety_margin=10,
                              count_tokens=lambda text: len(text))
    with pytest.raises(CoreError) as exc:
        budgeter.budget(system_text="s" * 50, question="q" * 50)
    assert exc.value.code == "PROMPT_BUDGET_EXCEEDED"


def test_history_capped_at_quarter_newest_pairs_chronological():
    counter = lambda text: len(text.split())  # noqa: E731
    history = [
        ChatMessage("user", "old question one two three four five"),
        ChatMessage("assistant", "old answer one two three four five"),
        ChatMessage("user", "mid question one two three four five"),
        ChatMessage("assistant", "mid answer one two three four five"),
        ChatMessage("user", "new question one two three four five"),
        ChatMessage("assistant", "new answer one two three four five"),
    ]
    # input=100, history allowance=25 words; each pair costs 16 -> only newest fits.
    tight = PromptBudgeter(context_window=120, max_output_tokens=10, safety_margin=10,
                           count_tokens=counter)
    result = tight.budget(system_text="sys", question="q", history=history)
    texts = [m.content for m in result.history]
    assert texts == ["new question one two three four five", "new answer one two three four five"]
    assert sum(counter(t) for t in texts) <= int(tight.input_budget * 0.25)


def test_context_fills_remainder_and_only_first_chunk_cuts():
    counter = lambda text: len(text)  # noqa: E731
    budgeter = PromptBudgeter(context_window=100, max_output_tokens=10, safety_margin=10,
                              count_tokens=counter)
    # input=80; system(3)+question(1)=4; history empty; remainder 76
    result = budgeter.budget(system_text="sys", question="q",
                             context_chunks=["a" * 50, "b" * 50])
    assert [s.index for s in result.context_slices] == [0]
    assert result.context_slices[0].truncated is False
    assert result.used_tokens <= result.input_budget
    # Nothing fits: first chunk cut, second dropped.
    tiny = PromptBudgeter(context_window=30, max_output_tokens=10, safety_margin=10,
                          count_tokens=counter)
    cut = tiny.budget(system_text="sys", question="q", context_chunks=["a" * 50, "b" * 50])
    assert len(cut.context_slices) == 1 and cut.context_slices[0].truncated is True


def test_sliced_citations_mirror_sent_slices_only():
    hits = [_hit("first chunk body"), _hit("second chunk body"), _hit("third chunk body")]
    slices = [(0, "first chunk body"), (2, "third chunk")]
    citations = resolve_sliced_citations(hits, slices)
    assert [c.citation_id for c in citations] == ["C1", "C2"]
    assert citations[1].excerpt == "third chunk"
    bundle = render_sliced_bundle(hits, slices)
    assert "[C1]" in bundle.text and "[C2]" in bundle.text and "[C3]" not in bundle.text
    assert "second chunk body" not in bundle.text
    assert [h.content for h in bundle.hits] == ["first chunk body", "third chunk"]


def test_validator_detects_invalid_and_uncited():
    report = validate_citations(
        "Claim one [C1]. Claim two [C99]. Bare claim.", inventory_ids={"C1"}
    )
    assert report.used_ids == ("C1", "C99")
    assert report.invalid_ids == ("C99",)
    assert report.cited_spans == 2 and report.uncited_spans == 1
    assert report.coverage == pytest.approx(2 / 3)
    clean = validate_citations("All cited [C1].", inventory_ids={"C1"})
    assert clean.invalid_ids == () and clean.coverage == 1.0
    malformed = validate_citations("Broken [Cx] and [C0] markers.", inventory_ids={"C1"})
    assert malformed.used_ids == ("C0",)


async def test_stream_applies_budget_and_observes_citations():
    from raghub_core.api import (
        RetrievalScope,
        StreamChatCommand,
        StreamRagChatUseCase,
    )
    from raghub_core.domain.providers.contracts import ChatStreamDelta

    from tests.core.fakes import FakeProviderResolver

    scope = RetrievalScope(uuid4(), uuid4())
    chatbots = _Chatbots(scope)
    retrieval = _Retrieval([_hit("word " * 500)])
    providers = FakeProviderResolver()
    providers.chat.deltas = [ChatStreamDelta(text="Answer with [C1] and [C9].")]
    conversations, usage = _Conversations(), _Usage()
    observed = []
    use_case = StreamRagChatUseCase(
        chatbots, retrieval, providers, conversations, usage,
        budgeter_factory=lambda model, ptype: PromptBudgeter(
            context_window=400, max_output_tokens=10, safety_margin=10,
            count_tokens=lambda text: len(text) // 4,
        ),
        citation_observer=lambda report: observed.append(report),
    )
    command = StreamChatCommand(scope.organization_id, chatbots.config.id, "What?")
    events = [event async for event in use_case.execute(command)]
    assert [type(event).__name__ for event in events] == [
        "ConversationStarted", "CitationsResolved", "TokenDelta",
        "UsageReported", "ChatCompleted",
    ]
    assert len(observed) == 1 and observed[0].invalid_ids == ("C9",)


async def test_stream_budget_overflow_is_terminal_error():
    from raghub_core.api import (
        RetrievalScope,
        StreamChatCommand,
        StreamRagChatUseCase,
    )

    from tests.core.fakes import FakeProviderResolver

    scope = RetrievalScope(uuid4(), uuid4())
    use_case = StreamRagChatUseCase(
        _Chatbots(scope), _Retrieval([_hit("content")]), FakeProviderResolver(),
        _Conversations(), _Usage(),
        budgeter_factory=lambda model, ptype: PromptBudgeter(
            context_window=30, max_output_tokens=10, safety_margin=10,
            count_tokens=lambda text: len(text),
        ),
    )
    command = StreamChatCommand(scope.organization_id, uuid4(), "What is this?")
    events = [event async for event in use_case.execute(command)]
    failed = [e for e in events if type(e).__name__ == "ChatFailed"]
    assert len(failed) == 1 and failed[0].code == "PROMPT_BUDGET_EXCEEDED"
    assert not [e for e in events if type(e).__name__ == "ChatCompleted"]


class _Chatbots:
    def __init__(self, scope):
        from raghub_core.api import ChatbotConfig

        self.config = ChatbotConfig(uuid4(), scope, "Bot", "Be helpful.", 5, True)

    async def get(self, organization_id, chatbot_id):
        return self.config


class _Retrieval:
    def __init__(self, hits):
        self.hits = hits

    async def retrieve(self, scope, question, limit):
        return self.hits[:limit]


class _Conversations:
    def __init__(self):
        self.id = uuid4()
        self.messages = []

    async def open(self, chatbot, conversation_id, external_user_id):
        return self.id

    async def add_user(self, conversation_id, content):
        self.messages.append(("user", content))
        return uuid4()

    async def history(self, conversation_id):
        from raghub_core.domain.providers.contracts import ChatMessage

        return [ChatMessage(*message) for message in self.messages]

    async def add_assistant(self, conversation_id, content, usage, citations):
        self.messages.append(("assistant", content))
        return uuid4()

    async def add_failed_assistant(self, conversation_id, content, error_code):
        return uuid4()

    async def commit(self):
        return None


class _Usage:
    async def record_chat_usage(self, record):
        return None
