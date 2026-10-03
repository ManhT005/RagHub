from app.application.chatbots.manage_chatbot import ManageChatbotUseCase
from app.application.chatbots.publish_chatbot import PublishChatbotUseCase
from app.infrastructure.chat_runtime import LazyProviderResolverAdapter
from app.infrastructure.persistence.chatbots import ChatbotRepositoryAdapter
from app.modules.ai_providers.resolver import ProviderResolver


def chatbot_management(session) -> ManageChatbotUseCase:
    repository = ChatbotRepositoryAdapter(session)
    providers = LazyProviderResolverAdapter(lambda: ProviderResolver(session))
    return ManageChatbotUseCase(repository, PublishChatbotUseCase(repository, providers))
