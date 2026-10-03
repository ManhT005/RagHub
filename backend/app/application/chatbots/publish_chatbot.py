from app.core_domain.chatbots.models import ChatbotRecord, CreateChatbotCommand
from app.core_domain.chatbots.policies import validate_chatbot_configuration
from app.core_domain.errors import CoreError
from app.ports.chatbots import ChatbotRepositoryPort
from app.ports.provider_resolver import ProviderResolverPort


class PublishChatbotUseCase:
    def __init__(self, repository: ChatbotRepositoryPort, providers: ProviderResolverPort) -> None:
        self.repository, self.providers = repository, providers

    async def validate(
        self, config: ChatbotRecord | CreateChatbotCommand, *, require_readiness: bool = True
    ) -> None:
        if not await self.repository.workspace_exists(config.scope):
            raise CoreError(
                "WORKSPACE_NOT_FOUND",
                "Workspace was not found in the current organization.",
            )
        if require_readiness:
            validate_chatbot_configuration(config)
            await self.providers.resolve_embedding(config.scope)
            await self.providers.resolve_chat(config.scope)

    async def execute(self, config: ChatbotRecord, *, published: bool = True) -> ChatbotRecord:
        from dataclasses import replace

        if published:
            await self.validate(config)
        return await self.repository.save(replace(config, published=published))
