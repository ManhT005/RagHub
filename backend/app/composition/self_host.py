"""Self-host wiring. Deployment choices never enter the reusable engine."""

from raghub_core.api import (
    ChatbotConfig,
    RetrievalScope,
    RetryDocumentUseCase,
    StreamRagChatUseCase,
    UploadDocumentUseCase,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.chatbots import chatbot_management
from app.composition.retrieval import retrieval_use_case
from app.core.config import Settings, get_settings
from app.infrastructure.chat_runtime import ChatbotRuntimeReader, LazyProviderResolverAdapter
from app.infrastructure.object_storage.minio import MinioObjectStorage
from app.infrastructure.persistence.chatbots import ChatbotRepositoryAdapter
from app.infrastructure.persistence.conversations import (
    ConversationRepositoryAdapter,
    UsageRecorderAdapter,
)
from app.infrastructure.persistence.uploads import (
    DocumentRetryRepositoryAdapter,
    UploadRepositoryAdapter,
)
from app.infrastructure.task_queue.queue import CeleryTaskQueue
from app.modules.ai_providers.resolver import ProviderResolver
from app.modules.documents.repository import DocumentRepository


class SelfHostContainer:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        *,
        storage=None,
        task_queue=None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.documents = DocumentRepository(session)
        self.chatbots = ChatbotRepositoryAdapter(session)
        self.storage = storage or MinioObjectStorage(self.settings)
        self.queue = task_queue or CeleryTaskQueue()

    def upload_document(self) -> UploadDocumentUseCase:
        return UploadDocumentUseCase(
            UploadRepositoryAdapter(self.documents, self.session),
            self.storage,
            self.queue,
            max_size_mb=self.settings.max_upload_size_mb,
        )

    def retry_document(self) -> RetryDocumentUseCase:
        return RetryDocumentUseCase(
            DocumentRetryRepositoryAdapter(self.documents, self.session),
            self.queue,
        )

    def retrieve_context(self):
        return retrieval_use_case(self.session)

    def manage_chatbots(self):
        return chatbot_management(self.session)

    async def chatbot_config(self, organization_id, chatbot_id) -> ChatbotConfig:
        record = await self.manage_chatbots().get(organization_id, chatbot_id)
        return ChatbotConfig(
            record.id,
            RetrievalScope(record.organization_id, record.workspace_id),
            record.name,
            record.system_prompt,
            record.retrieval_limit,
            record.published,
            record.model,
        )

    def stream_chat(self, *, chatbot_loader=None, conversation_loader=None, history_loader=None):
        return StreamRagChatUseCase(
            ChatbotRuntimeReader(chatbot_loader) if chatbot_loader else self,
            self.retrieve_context(),
            LazyProviderResolverAdapter(lambda: ProviderResolver(self.session)),
            ConversationRepositoryAdapter(
                self.session,
                conversation_loader=conversation_loader,
                history_loader=history_loader,
            ),
            UsageRecorderAdapter(self.session),
        )

    async def get(self, organization_id, chatbot_id):
        return await self.chatbot_config(organization_id, chatbot_id)

    def run_ingestion(self):
        from app.composition.worker import WorkerContainer

        return WorkerContainer(self.session, self.settings).run_ingestion()
