from typing import Protocol
from uuid import UUID

from app.core_domain.chatbots.models import ChatbotConfig


class ChatbotReadPort(Protocol):
    async def get(self, organization_id: UUID, chatbot_id: UUID) -> ChatbotConfig: ...
