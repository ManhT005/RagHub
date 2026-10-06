from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import aclosing
from time import perf_counter as _perf_now
from uuid import UUID

from raghub_core.domain.chatbots.models import ChatbotConfig
from raghub_core.domain.errors import CoreError
from raghub_core.domain.providers.contracts import ChatMessage, ChatOptions, ChatUsage
from raghub_core.domain.providers.usage import estimate_chat_usage
from raghub_core.domain.rag.citation_validator import CitationReport, validate_citations
from raghub_core.domain.rag.citations import (
    render_sliced_bundle,
    resolve_sliced_citations,
    resolve_trusted_citations,
)
from raghub_core.domain.rag.clarification import ClarificationPolicy, normalize_query
from raghub_core.domain.rag.events import (
    ChatCompleted,
    ChatFailed,
    CitationsResolved,
    ClarificationRequested,
    ConversationStarted,
    RagEvent,
    TokenDelta,
    UsageReported,
)
from raghub_core.domain.rag.intent import IntentAction
from raghub_core.domain.rag.models import ChatUsageRecord, StreamChatCommand
from raghub_core.domain.rag.prompt import EMPTY_CONTEXT_ANSWER, build_prompt
from raghub_core.domain.rag.prompt_budget import BudgetedPrompt, PromptBudgeter
from raghub_core.domain.rag.timing import ChatStreamTiming
from raghub_core.domain.retrieval.hybrid import build_context_bundle
from raghub_core.ports.chatbots import ChatbotReadPort
from raghub_core.ports.conversations import ConversationRepositoryPort
from raghub_core.ports.provider_resolver import ProviderResolverPort
from raghub_core.ports.retrieval import RetrievalPort
from raghub_core.ports.telemetry import TelemetryPort
from raghub_core.ports.usage import UsageRecorderPort


class StreamRagChatUseCase:
    def __init__(
        self,
        chatbots: ChatbotReadPort,
        retrieval: RetrievalPort,
        providers: ProviderResolverPort,
        conversations: ConversationRepositoryPort,
        usage: UsageRecorderPort,
        *,
        timing_factory: Callable[[], ChatStreamTiming] = ChatStreamTiming,
        budgeter_factory: Callable[[str, str], PromptBudgeter] | None = None,
        citation_observer: Callable[[CitationReport], None] | None = None,
        telemetry: TelemetryPort | None = None,
        clarification_policy: ClarificationPolicy | None = None,
        clarification_mode: str = "conservative",
        max_clarifying_turns: int = 1,
    ) -> None:
        self.chatbots, self.retrieval, self.providers = chatbots, retrieval, providers
        self.conversations, self.usage, self.timing_factory = conversations, usage, timing_factory
        self.budgeter_factory = budgeter_factory
        self.citation_observer = citation_observer
        self.telemetry = telemetry
        self.clarification_policy = clarification_policy or ClarificationPolicy()
        self.clarification_mode = clarification_mode
        self.max_clarifying_turns = max_clarifying_turns

    async def execute(self, command: StreamChatCommand) -> AsyncIterator[RagEvent]:
        chatbot = await self.chatbots.get(command.organization_id, command.chatbot_id)
        if chatbot.scope.organization_id != command.organization_id:
            raise CoreError(
                "CHATBOT_NOT_FOUND",
                "Chatbot was not found in the current organization.",
            )
        if not chatbot.published:
            raise CoreError("CHATBOT_NOT_PUBLISHED", "Chatbot is not published.")
        conversation_id = await self.conversations.open(
            chatbot,
            command.conversation_id,
            command.external_user_id,
        )
        previous_history = await self.conversations.history(conversation_id)
        user_message_id = await self.conversations.add_user(conversation_id, command.question)
        # The submitted question remains durable even when provider resolution/generation fails.
        await self.conversations.commit()
        yield ConversationStarted(conversation_id, user_message_id)
        answer: list[str] = []
        try:
            async with aclosing(
                self._answer(command, chatbot, conversation_id, previous_history, answer)
            ) as stream:
                async for event in stream:
                    yield event
        except (CoreError, TimeoutError) as exc:
            error = (
                exc
                if isinstance(exc, CoreError)
                else CoreError("PROVIDER_TIMEOUT", "The AI provider timed out.")
            )
            await self.conversations.add_failed_assistant(
                conversation_id, "".join(answer), error.code
            )
            await self.conversations.commit()
            yield ChatFailed(error.code, error.message)

    async def _answer(
        self,
        command: StreamChatCommand,
        chatbot: ChatbotConfig,
        conversation_id: UUID,
        previous_history: Sequence[ChatMessage],
        answer: list[str],
    ) -> AsyncIterator[RagEvent]:
        question = self._resolved_question(command.question, previous_history)
        decision = self.clarification_policy.evaluate(
            question,
            domain_profile=chatbot.domain_profile,
            mode=chatbot.clarification_mode or self.clarification_mode,
            clarifying_turns=self._clarifying_turns(previous_history),
            max_clarifying_turns=chatbot.max_clarifying_turns,
        )
        if decision.action is IntentAction.CLARIFY:
            usage = ChatUsage(0, 0, 0, "none")
            message_id = await self.conversations.add_assistant(
                conversation_id,
                decision.message,
                usage,
                (),
            )
            await self.conversations.commit()
            yield ClarificationRequested(
                decision.message,
                decision.missing_slots,
                decision.suggestions,
                decision.reason,
            )
            yield UsageReported(usage)
            yield ChatCompleted(message_id, None, 0)
            return
        if decision.action is IntentAction.REFUSE_OR_REDIRECT:
            message = decision.message or "I can only answer from the provided documents."
            usage = ChatUsage(0, 0, 0, "none")
            message_id = await self.conversations.add_assistant(
                conversation_id,
                message,
                usage,
                (),
            )
            await self.conversations.commit()
            yield CitationsResolved(())
            yield TokenDelta(message)
            yield UsageReported(usage)
            yield ChatCompleted(message_id, None, 0)
            return

        hits = await self.retrieval.retrieve(chatbot.scope, question, chatbot.retrieval_limit)
        if not hits:
            usage = ChatUsage(0, 0, 0, "none")
            message_id = await self.conversations.add_assistant(
                conversation_id,
                EMPTY_CONTEXT_ANSWER,
                usage,
                (),
            )
            await self.conversations.commit()
            yield CitationsResolved(())
            yield TokenDelta(EMPTY_CONTEXT_ANSWER)
            yield UsageReported(usage)
            yield ChatCompleted(message_id, None, 0)
            return
        runtime = await self.providers.resolve_chat(chatbot.scope)
        mark = _perf_now()
        context = build_context_bundle(hits)
        if self.telemetry is not None:
            self.telemetry.timing("context", (_perf_now() - mark) * 1000, {})
        budgeted: BudgetedPrompt | None = None
        if self.budgeter_factory is not None:
            budgeter = self.budgeter_factory(chatbot.model or runtime.model, runtime.provider_type)
            budgeted = budgeter.budget(
                system_text=chatbot.system_prompt,
                question=question,
                history=previous_history,
                context_chunks=[hit.content for hit in context.hits],
            )
        if budgeted is None:
            citations = resolve_trusted_citations(context.hits[:5])
            inventory = {citation.citation_id for citation in citations}
            mark = _perf_now()
            messages = build_prompt(
                chatbot.system_prompt,
                question,
                context,
                previous_history,
            )
            if self.telemetry is not None:
                self.telemetry.timing("prompt", (_perf_now() - mark) * 1000, {})
        else:
            slice_pairs = [(s.index, s.text) for s in budgeted.context_slices]
            citations = resolve_sliced_citations(context.hits, slice_pairs)
            inventory = {citation.citation_id for citation in citations}
            sliced_bundle = render_sliced_bundle(context.hits, slice_pairs)
            mark = _perf_now()
            messages = build_prompt(
                budgeted.system_text,
                budgeted.question,
                sliced_bundle,
                budgeted.history,
            )
            if self.telemetry is not None:
                self.telemetry.timing("prompt", (_perf_now() - mark) * 1000, {})
        yield CitationsResolved(citations)
        timing = self.timing_factory()
        usage: ChatUsage | None = None
        stream = runtime.provider.stream_chat(
            messages, ChatOptions(model=chatbot.model or runtime.model)
        )
        try:
            async for delta in stream:
                if delta.text:
                    timing.record_token()
                    answer.append(delta.text)
                    yield TokenDelta(delta.text)
                if delta.usage:
                    usage = delta.usage
        except (CoreError, TimeoutError):
            raise
        except Exception as exc:
            raise CoreError("CHAT_RUNTIME_FAILED", "Chat generation failed.") from exc
        finally:
            close = getattr(stream, "aclose", None)
            if close:
                await close()
        usage = usage or estimate_chat_usage(messages, "".join(answer))
        if self.citation_observer is not None or self.telemetry is not None:
            # Observe-only: metrics and release gates consume this; stream is untouched.
            report = validate_citations("".join(answer), inventory_ids=inventory)
            if self.citation_observer is not None:
                self.citation_observer(report)
            if self.telemetry is not None:
                self.telemetry.counter(
                    "citation_invalid", {"stage": "citation"}, len(report.invalid_ids)
                )
                self.telemetry.counter(
                    "citation_coverage_pct", {"stage": "citation"}, int(report.coverage * 100)
                )
        message_id = await self.conversations.add_assistant(
            conversation_id,
            "".join(answer),
            usage,
            citations,
        )
        latency_ms = timing.elapsed_ms()
        await self.usage.record_chat_usage(
            ChatUsageRecord(
                chatbot.scope,
                message_id,
                runtime.provider_type,
                chatbot.model or runtime.model,
                usage,
                timing.first_token_ms,
                latency_ms,
            )
        )
        await self.conversations.commit()
        yield UsageReported(usage)
        yield ChatCompleted(message_id, timing.first_token_ms, latency_ms)

    def _resolved_question(self, question: str, history: Sequence[ChatMessage]) -> str:
        pending = self._pending_clarification(history)
        if pending is None:
            return question
        return f"{pending} {question}".strip()

    def _pending_clarification(self, history: Sequence[ChatMessage]) -> str | None:
        if len(history) < 2:
            return None
        previous_user, last_assistant = history[-2], history[-1]
        if previous_user.role != "user" or not self._is_clarification_message(last_assistant):
            return None
        return previous_user.content

    def _clarifying_turns(self, history: Sequence[ChatMessage]) -> int:
        return sum(1 for message in history if self._is_clarification_message(message))

    def _is_clarification_message(self, message: ChatMessage) -> bool:
        if message.role != "assistant":
            return False
        return normalize_query(message.content).startswith("ban vui long cho biet them ")
