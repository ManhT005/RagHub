"""Stable host-facing facade for Core use cases, commands, values and events.

Host composition imports public use cases here. Infrastructure implements ports
directly and may import their domain contracts; helpers stay in their modules.
This facade only re-exports Core symbols and never constructs host adapters.
"""

from raghub_core.application.chatbots.manage_chatbot import ManageChatbotUseCase
from raghub_core.application.chatbots.publish_chatbot import PublishChatbotUseCase
from raghub_core.application.documents.retry_document import RetryDocumentUseCase
from raghub_core.application.documents.upload_document import UploadDocumentUseCase
from raghub_core.application.ingestion.build_document_index import BuildDocumentIndexUseCase
from raghub_core.application.ingestion.reindex_workspace import ReindexWorkspaceUseCase
from raghub_core.application.ingestion.run_ingestion import RunIngestionUseCase
from raghub_core.application.rag.stream_chat import StreamRagChatUseCase
from raghub_core.application.retrieval.retrieve_context import RetrieveContextUseCase
from raghub_core.domain.chatbots.models import (
    ChatbotConfig,
    ChatbotRecord,
    CreateChatbotCommand,
    PatchChatbotCommand,
)
from raghub_core.domain.documents.upload import UploadDocumentCommand, UploadReceipt
from raghub_core.domain.errors import CoreError
from raghub_core.domain.rag.events import (
    ChatCompleted,
    ChatFailed,
    CitationsResolved,
    ClarificationRequested,
    ConversationStarted,
    RagEvent,
    TokenDelta,
    UsageReported,
)
from raghub_core.domain.rag.models import StreamChatCommand
from raghub_core.domain.retrieval.hybrid import ContextBundle
from raghub_core.domain.retrieval.models import RetrievalScope, RetrievedChunk

__all__ = [
    "BuildDocumentIndexUseCase",
    "ChatCompleted",
    "ChatFailed",
    "ChatbotConfig",
    "ChatbotRecord",
    "CitationsResolved",
    "ClarificationRequested",
    "ContextBundle",
    "ConversationStarted",
    "CoreError",
    "CreateChatbotCommand",
    "ManageChatbotUseCase",
    "PatchChatbotCommand",
    "PublishChatbotUseCase",
    "RagEvent",
    "ReindexWorkspaceUseCase",
    "RetrievalScope",
    "RetrieveContextUseCase",
    "RetrievedChunk",
    "RetryDocumentUseCase",
    "RunIngestionUseCase",
    "StreamChatCommand",
    "StreamRagChatUseCase",
    "TokenDelta",
    "UploadDocumentCommand",
    "UploadDocumentUseCase",
    "UploadReceipt",
    "UsageReported",
]
