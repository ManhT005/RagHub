"""Real PostgreSQL proves the use case's durable question/failure transaction policy."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from raghub_core.application.rag.stream_chat import StreamRagChatUseCase
from raghub_core.domain.chatbots.models import ChatbotConfig
from raghub_core.domain.providers.contracts import ChatMessage, ChatStreamDelta
from raghub_core.domain.providers.errors import ProviderUnavailableError
from raghub_core.domain.rag.events import ChatCompleted, ChatFailed, ConversationStarted
from raghub_core.domain.rag.models import StreamChatCommand
from raghub_core.domain.retrieval.models import RetrievalScope, RetrievedChunk
from raghub_core.ports.provider_resolver import ChatRuntime
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.infrastructure.persistence.conversations import ConversationRepositoryAdapter
from app.modules.chatbots.models import Chatbot, Message, UsageEvent
from app.modules.organizations.models import Organization
from app.modules.workspaces.models import Workspace

pytestmark = pytest.mark.integration


async def test_provider_failure_keeps_committed_question_and_failed_partial_out_of_history():
    database = os.getenv("RAGHUB_TEST_DATABASE_URL")
    if not database:
        pytest.skip("Set RAGHUB_TEST_DATABASE_URL to a migrated test database.")
    engine = create_async_engine(database, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    scope = RetrievalScope(uuid4(), uuid4())
    chatbot_id = uuid4()
    try:
        async with sessions() as session:
            session.add(Organization(id=scope.organization_id, name="Core", slug=uuid4().hex))
            await session.flush()
            session.add(
                Workspace(
                    id=scope.workspace_id,
                    organization_id=scope.organization_id,
                    name="Core",
                    slug="core",
                )
            )
            await session.flush()
            session.add(
                Chatbot(
                    id=chatbot_id,
                    organization_id=scope.organization_id,
                    workspace_id=scope.workspace_id,
                    name="Core",
                    published=True,
                )
            )
            await session.commit()

        question = "current question"
        checked = []

        class Provider:
            async def stream_chat(self, messages, options):
                assert messages[-1] == ChatMessage("user", question)
                assert sum(message.content == question for message in messages) == 1
                # A separate transaction must see the question before generation starts.
                async with sessions() as observer:
                    stored = await observer.scalar(
                        select(Message).where(Message.role == "user", Message.content == question)
                    )
                    assert stored is not None
                    checked.append(stored.conversation_id)
                yield ChatStreamDelta(text="partial answer")
                raise ProviderUnavailableError()

        config = ChatbotConfig(chatbot_id, scope, "Core", "Be concise.", 5, True)
        hit = RetrievedChunk(uuid4(), uuid4(), uuid4(), "knowledge", "guide.md", None, None, 1.0)
        async with sessions() as session:
            repository = ConversationRepositoryAdapter(session)
            usage = SimpleNamespace(record_chat_usage=AsyncMock())
            use_case = StreamRagChatUseCase(
                SimpleNamespace(get=AsyncMock(return_value=config)),
                SimpleNamespace(retrieve=AsyncMock(return_value=[hit])),
                SimpleNamespace(
                    resolve_chat=AsyncMock(return_value=ChatRuntime(Provider(), "TEST", "test"))
                ),
                repository,
                usage,
            )
            events = [
                event
                async for event in use_case.execute(
                    StreamChatCommand(scope.organization_id, chatbot_id, question)
                )
            ]
            assert isinstance(events[0], ConversationStarted)
            assert events[-1] == ChatFailed(
                "PROVIDER_UNAVAILABLE", "The AI provider is unavailable."
            )
            assert not any(isinstance(event, ChatCompleted) for event in events)
            usage.record_chat_usage.assert_not_awaited()
            history = await repository.history(events[0].conversation_id)
            assert history == [ChatMessage("user", question)]

        async with sessions() as session:
            messages = list(
                await session.scalars(
                    select(Message)
                    .where(Message.conversation_id == checked[0])
                    .order_by(Message.created_at, Message.id)
                )
            )
            assert len(messages) == 2
            failed = next(message for message in messages if message.role == "assistant")
            assert failed.content == "partial answer"
            assert failed.usage_json == {"status": "FAILED", "error_code": "PROVIDER_UNAVAILABLE"}
            assert (
                await session.scalar(select(UsageEvent).where(UsageEvent.message_id == failed.id))
                is None
            )
    finally:
        async with sessions() as session:
            await session.execute(
                delete(Organization).where(Organization.id == scope.organization_id)
            )
            await session.commit()
        await engine.dispose()
