from app.infrastructure.chat_runtime import (
    ChatbotRuntimeReader,
    LazyProviderResolverAdapter,
    RuntimeRetrievalAdapter,
)
from app.infrastructure.persistence.conversations import (
    ConversationRepositoryAdapter,
    UsageRecorderAdapter,
)
from raghub_core.application.rag.stream_chat import StreamRagChatUseCase


def rag_use_case(
    session, chatbot_loader, conversation_loader, history_loader, search_factory, resolver_factory
) -> StreamRagChatUseCase:
    return StreamRagChatUseCase(
        ChatbotRuntimeReader(chatbot_loader),
        RuntimeRetrievalAdapter(search_factory),
        LazyProviderResolverAdapter(resolver_factory),
        ConversationRepositoryAdapter(
            session, conversation_loader=conversation_loader, history_loader=history_loader
        ),
        UsageRecorderAdapter(session),
    )
