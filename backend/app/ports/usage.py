from typing import Protocol

from app.core_domain.rag.models import ChatUsageRecord


class UsageRecorderPort(Protocol):
    async def record_chat_usage(self, record: ChatUsageRecord) -> None: ...
