from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.chatbots.manage_chatbot import ManageChatbotUseCase
from app.application.chatbots.publish_chatbot import PublishChatbotUseCase
from raghub_core.domain.chatbots.models import (
    ChatbotRecord,
    CreateChatbotCommand,
    PatchChatbotCommand,
)
from raghub_core.domain.errors import CoreError
from raghub_core.domain.retrieval.models import RetrievalScope

from .fakes import FakeProviderResolver


class Repository:
    def __init__(self):
        self.exists = True
        self.saved = []
        self.record = ChatbotRecord(
            uuid4(), uuid4(), uuid4(), "Bot", "Prompt", "model", 5, False, datetime.now(UTC), None
        )

    async def workspace_exists(self, scope):
        return self.exists

    async def get(self, organization_id, chatbot_id):
        if organization_id == self.record.organization_id and chatbot_id == self.record.id:
            return self.record
        return None

    async def list(self, scope):
        return [self.record] if scope == self.record.scope else []

    async def create(self, command):
        self.record = replace(
            self.record,
            organization_id=command.scope.organization_id,
            workspace_id=command.scope.workspace_id,
            name=command.name,
            system_prompt=command.system_prompt,
            model=command.model,
            retrieval_limit=command.retrieval_limit,
            published=command.published,
        )
        return self.record

    async def save(self, record):
        self.saved.append(record)
        self.record = record
        return record

    async def delete(self, record):
        self.deleted = record


async def test_management_uses_typed_commands_and_preserves_omitted_patch_fields():
    repository, providers = Repository(), FakeProviderResolver()
    use_case = ManageChatbotUseCase(repository, PublishChatbotUseCase(repository, providers))
    scope = RetrievalScope(uuid4(), uuid4())
    record = await use_case.create(CreateChatbotCommand(scope, " Bot ", " Prompt ", "model"))
    assert record.name == "Bot" and record.system_prompt == "Prompt" and not record.published
    patched = await use_case.update(
        scope.organization_id, record.id, PatchChatbotCommand(model=None)
    )
    assert patched.model is None and patched.name == record.name and patched.retrieval_limit == 5


async def test_existing_publication_mode_and_strict_readiness_gate_are_explicit():
    repository, providers = Repository(), FakeProviderResolver()
    publication = PublishChatbotUseCase(repository, providers)
    manage = ManageChatbotUseCase(repository, publication)
    record = await manage.update(
        repository.record.organization_id, repository.record.id, PatchChatbotCommand(published=True)
    )
    assert record.published and not providers.scopes and not providers.chat_scopes
    await publication.execute(record)
    assert providers.scopes == providers.chat_scopes == [record.scope]


async def test_strict_publication_rejects_missing_workspace_or_invalid_config():
    repository, providers = Repository(), FakeProviderResolver()
    publication = PublishChatbotUseCase(repository, providers)
    repository.exists = False
    with pytest.raises(CoreError) as error:
        await publication.execute(repository.record)
    assert error.value.code == "WORKSPACE_NOT_FOUND"
    repository.exists = True
    with pytest.raises(CoreError) as error:
        await publication.execute(replace(repository.record, name=" "))
    assert error.value.code == "INVALID_CHATBOT_CONFIG" and not repository.saved


async def test_chatbot_management_cannot_read_another_tenant():
    repository, providers = Repository(), FakeProviderResolver()
    manage = ManageChatbotUseCase(repository, PublishChatbotUseCase(repository, providers))
    with pytest.raises(CoreError) as error:
        await manage.get(uuid4(), repository.record.id)
    assert error.value.code == "CHATBOT_NOT_FOUND"
