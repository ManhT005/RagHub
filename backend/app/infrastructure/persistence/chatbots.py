from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core_domain.chatbots.models import ChatbotRecord, CreateChatbotCommand
from app.core_domain.retrieval.models import RetrievalScope
from app.modules.chatbots.models import Chatbot
from app.modules.workspaces.models import Workspace


def chatbot_record(chatbot: Chatbot) -> ChatbotRecord:
    return ChatbotRecord(
        chatbot.id,
        chatbot.organization_id,
        chatbot.workspace_id,
        chatbot.name,
        chatbot.system_prompt,
        chatbot.model,
        chatbot.retrieval_limit,
        chatbot.published,
        chatbot.created_at,
        chatbot.updated_at,
    )


class ChatbotRepositoryAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def workspace_exists(self, scope: RetrievalScope) -> bool:
        return (
            await self.session.scalar(
                select(Workspace.id).where(
                    Workspace.id == scope.workspace_id,
                    Workspace.organization_id == scope.organization_id,
                    Workspace.deleted_at.is_(None),
                )
            )
            is not None
        )

    async def list(self, scope: RetrievalScope) -> list[ChatbotRecord]:
        rows = await self.session.scalars(
            select(Chatbot)
            .where(
                Chatbot.organization_id == scope.organization_id,
                Chatbot.workspace_id == scope.workspace_id,
            )
            .order_by(Chatbot.name)
        )
        return [chatbot_record(row) for row in rows]

    async def _get(self, organization_id, chatbot_id):
        return await self.session.scalar(
            select(Chatbot).where(
                Chatbot.id == chatbot_id,
                Chatbot.organization_id == organization_id,
            )
        )

    async def get(self, organization_id, chatbot_id) -> ChatbotRecord | None:
        row = await self._get(organization_id, chatbot_id)
        return chatbot_record(row) if row else None

    async def create(self, command: CreateChatbotCommand) -> ChatbotRecord:
        chatbot = Chatbot(
            organization_id=command.scope.organization_id,
            workspace_id=command.scope.workspace_id,
            name=command.name,
            system_prompt=command.system_prompt,
            model=command.model,
            retrieval_limit=command.retrieval_limit,
            published=command.published,
        )
        self.session.add(chatbot)
        await self.session.commit()
        await self.session.refresh(chatbot)
        return chatbot_record(chatbot)

    async def save(self, record: ChatbotRecord) -> ChatbotRecord:
        row = await self._get(record.organization_id, record.id)
        for name in ("name", "system_prompt", "model", "retrieval_limit", "published"):
            setattr(row, name, getattr(record, name))
        await self.session.commit()
        await self.session.refresh(row)
        return chatbot_record(row)

    async def delete(self, record: ChatbotRecord) -> None:
        await self.session.delete(await self._get(record.organization_id, record.id))
        await self.session.commit()
