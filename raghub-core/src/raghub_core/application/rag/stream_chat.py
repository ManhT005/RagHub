from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import aclosing
from uuid import UUID

from raghub_core.domain.chatbots.models import ChatbotConfig
from raghub_core.domain.errors import CoreError
from raghub_core.domain.providers.contracts import ChatMessage, ChatOptions, ChatUsage
from raghub_core.domain.providers.usage import estimate_chat_usage
from raghub_core.domain.rag.citations import resolve_trusted_citations
from raghub_core.domain.rag.events import (
    ChatCompleted,
    ChatFailed,
    CitationsResolved,
    ConversationStarted,
    RagEvent,
    TokenDelta,
    UsageReported,
)
from raghub_core.domain.rag.models import ChatUsageRecord, StreamChatCommand
from raghub_core.domain.rag.prompt import EMPTY_CONTEXT_ANSWER, build_prompt
from raghub_core.domain.rag.timing import ChatStreamTiming
from raghub_core.domain.retrieval.hybrid import build_context_bundle
from raghub_core.ports.chatbots import ChatbotReadPort
from raghub_core.ports.conversations import ConversationRepositoryPort
from raghub_core.ports.provider_resolver import ProviderResolverPort
from raghub_core.ports.retrieval import RetrievalPort
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
    ) -> None:
        self.chatbots, self.retrieval, self.providers = chatbots, retrieval, providers
        self.conversations, self.usage, self.timing_factory = conversations, usage, timing_factory

    async def execute(self, command: StreamChatCommand) -> AsyncIterator[RagEvent]:
        chatbot = await self.chatbots.get(command.organization_id, command.chatbot_id)
        if chatbot.scope.organization_id != command.organization_id:
            raise CoreError(
                "CHATBOT_NOT_FOUND",
                "Chatbot was not found in the current organization.",
            )
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
        hits = await self.retrieval.retrieve(
            chatbot.scope, command.question, chatbot.retrieval_limit
        )
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
        context = build_context_bundle(hits)
        citations = resolve_trusted_citations(context.hits)
        yield CitationsResolved(citations)
        messages = build_prompt(
            chatbot.system_prompt,
            command.question,
            context,
            previous_history,
        )
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
