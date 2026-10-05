from dataclasses import fields, replace
from uuid import UUID

from raghub_core.application.chatbots.publish_chatbot import PublishChatbotUseCase
from raghub_core.domain.chatbots.models import (
    ChatbotRecord,
    CreateChatbotCommand,
    PatchChatbotCommand,
    Unset,
)
from raghub_core.domain.errors import CoreError
from raghub_core.domain.retrieval.models import RetrievalScope
from raghub_core.ports.chatbots import ChatbotRepositoryPort


class ManageChatbotUseCase:
    def __init__(
        self, repository: ChatbotRepositoryPort, publication: PublishChatbotUseCase
    ) -> None:
        self.repository, self.publication = repository, publication

    async def _workspace(self, scope: RetrievalScope) -> None:
        if not await self.repository.workspace_exists(scope):
            raise CoreError(
                "WORKSPACE_NOT_FOUND",
                "Workspace was not found in the current organization.",
            )

    async def list(self, scope: RetrievalScope) -> list[ChatbotRecord]:
        await self._workspace(scope)
        return await self.repository.list(scope)

    async def get(self, organization_id: UUID, chatbot_id: UUID) -> ChatbotRecord:
        record = await self.repository.get(organization_id, chatbot_id)
        if record is None:
            raise CoreError(
                "CHATBOT_NOT_FOUND",
                "Chatbot was not found in the current organization.",
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
