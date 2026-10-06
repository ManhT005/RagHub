from raghub_core.api import StreamRagChatUseCase
from raghub_core.domain.rag.model_profile import (
    count_tokens_exact,
)
from raghub_core.domain.rag.prompt_budget import PromptBudgeter

from app.core.config import get_settings
from app.infrastructure.chat_runtime import (
    ChatbotRuntimeReader,
    LazyProviderResolverAdapter,
    RuntimeRetrievalAdapter,
)
from app.infrastructure.persistence.conversations import (
    ConversationRepositoryAdapter,
    UsageRecorderAdapter,
)
from app.infrastructure.telemetry.adapter import LoggingTelemetry
from app.modules.ai_providers.model_profiles import resolve_profile
from app.modules.rag_policies.clarification import HostClarificationPolicy


def prompt_budgeter_factory(model: str, provider_type: str) -> PromptBudgeter:
    """Build the global prompt budgeter from the model profile and settings."""
    settings = get_settings()
    resolved = resolve_profile(model, context_window=settings.rag_model_context_window)
    counter = count_tokens_exact if resolved.profile.exact_tokenizer else None
    if counter is None:
        from raghub_core.domain.rag.model_profile import count_tokens_fallback

        counter = count_tokens_fallback
    return PromptBudgeter(
        context_window=resolved.profile.context_window,
        max_output_tokens=settings.rag_max_output_tokens,
        safety_margin=settings.rag_prompt_safety_margin,
        count_tokens=counter,
    )


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
        budgeter_factory=prompt_budgeter_factory,
        telemetry=LoggingTelemetry(),
        clarification_policy=HostClarificationPolicy(),
    )
