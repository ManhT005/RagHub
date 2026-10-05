from typing import Protocol

from raghub_core.domain.rag.models import ChatUsageRecord


class UsageRecorderPort(Protocol):
    async def record_chat_usage(self, record: ChatUsageRecord) -> None: ...
