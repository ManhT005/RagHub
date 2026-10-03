from dataclasses import fields, replace
from uuid import UUID

from app.application.chatbots.publish_chatbot import PublishChatbotUseCase
from app.core_domain.chatbots.models import (
    ChatbotRecord,
    CreateChatbotCommand,
    PatchChatbotCommand,
    Unset,
)
from app.core_domain.errors import AppError
from app.core_domain.retrieval.models import RetrievalScope
from app.ports.chatbots import ChatbotRepositoryPort


class ManageChatbotUseCase:
    def __init__(
        self, repository: ChatbotRepositoryPort, publication: PublishChatbotUseCase
    ) -> None:
        self.repository, self.publication = repository, publication

    async def _workspace(self, scope: RetrievalScope) -> None:
        if not await self.repository.workspace_exists(scope):
            raise AppError(
                "WORKSPACE_NOT_FOUND",
                "Workspace was not found in the current organization.",
                status_code=404,
            )

    async def list(self, scope: RetrievalScope) -> list[ChatbotRecord]:
        await self._workspace(scope)
        return await self.repository.list(scope)

    async def get(self, organization_id: UUID, chatbot_id: UUID) -> ChatbotRecord:
        record = await self.repository.get(organization_id, chatbot_id)
        if record is None:
            raise AppError(
                "CHATBOT_NOT_FOUND",
                "Chatbot was not found in the current organization.",
                status_code=404,
            )
        return record

    async def create(self, command: CreateChatbotCommand) -> ChatbotRecord:
        await self._workspace(command.scope)
        command = replace(
            command, name=command.name.strip(), system_prompt=command.system_prompt.strip()
        )
        if command.published:
            # The existing authenticated API permits publication before provider setup.
            # New control planes can call PublishChatbotUseCase.execute for a readiness gate.
            await self.publication.validate(command, require_readiness=False)
        return await self.repository.create(command)

    async def update(
        self, organization_id: UUID, chatbot_id: UUID, patch: PatchChatbotCommand
    ) -> ChatbotRecord:
        record = await self.get(organization_id, chatbot_id)
        changes = {}
        for field in fields(patch):
            value = getattr(patch, field.name)
            if value is not Unset.VALUE:
                changes[field.name] = value.strip() if isinstance(value, str) else value
        result = replace(record, **changes)
        if changes.get("published"):
            await self.publication.validate(result, require_readiness=False)
        return await self.repository.save(result)

    async def delete(self, organization_id: UUID, chatbot_id: UUID) -> None:
        await self.repository.delete(await self.get(organization_id, chatbot_id))
