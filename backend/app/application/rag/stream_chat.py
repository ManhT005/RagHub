from collections.abc import AsyncIterator, Callable

from app.core_domain.errors import AppError
from app.core_domain.providers.contracts import ChatOptions, ChatUsage
from app.core_domain.providers.usage import estimate_chat_usage
from app.core_domain.rag.citations import resolve_trusted_citations
from app.core_domain.rag.events import (
    ChatCompleted,
    ChatFailed,
    CitationsResolved,
    ConversationStarted,
    RagEvent,
    TokenDelta,
    UsageReported,
)
from app.core_domain.rag.models import ChatUsageRecord, StreamChatCommand
from app.core_domain.rag.prompt import EMPTY_CONTEXT_ANSWER, build_prompt
from app.core_domain.rag.timing import ChatStreamTiming
from app.core_domain.retrieval.hybrid import build_context_bundle
from app.core_domain.retrieval.models import RetrievedChunk
from app.ports.chatbots import ChatbotReadPort
from app.ports.conversations import ConversationRepositoryPort
from app.ports.provider_resolver import ProviderResolverPort
from app.ports.retrieval import RetrievalPort
from app.ports.usage import UsageRecorderPort


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
            raise AppError(
                "CHATBOT_NOT_FOUND",
                "Chatbot was not found in the current organization.",
                status_code=404,
            )
        if not chatbot.published:
            raise AppError("CHATBOT_NOT_PUBLISHED", "Chatbot is not published.", status_code=409)
        hits = await self.retrieval.retrieve(
            chatbot.scope, command.question, chatbot.retrieval_limit
        )
        conversation_id = await self.conversations.open(
            chatbot,
            command.conversation_id,
            command.external_user_id,
        )
        user_message_id = await self.conversations.add_user(conversation_id, command.question)
        if not hits:
            usage = ChatUsage(0, 0, 0, "none")
            message_id = await self.conversations.add_assistant(
                conversation_id,
                EMPTY_CONTEXT_ANSWER,
                usage,
                (),
            )
            await self.conversations.commit()
            yield ConversationStarted(conversation_id, user_message_id)
            yield CitationsResolved(())
            yield TokenDelta(EMPTY_CONTEXT_ANSWER)
            yield UsageReported(usage)
            yield ChatCompleted(message_id, None, 0)
            return
        runtime = await self.providers.resolve_chat(chatbot.scope)
        context = build_context_bundle([hit.as_hit() for hit in hits])
        selected = [RetrievedChunk.from_hit(hit) for hit in context.hits]
        citations = resolve_trusted_citations(selected)
        yield ConversationStarted(conversation_id, user_message_id)
        yield CitationsResolved(citations)
        messages = build_prompt(
            chatbot.system_prompt,
            command.question,
            context,
            await self.conversations.history(conversation_id),
        )
        timing = self.timing_factory()
        answer: list[str] = []
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
        except AppError as exc:
            yield ChatFailed(exc.code, exc.message)
            return
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
