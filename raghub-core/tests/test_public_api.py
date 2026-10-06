"""Freeze the supported host facade independently of host/runtime installation."""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from raghub_core import api

# Deliberately independent of api.__all__: removal or accidental expansion fails.
PUBLIC_CONTRACTS = {
    "application.documents.upload_document": ("UploadDocumentUseCase",),
    "application.documents.retry_document": ("RetryDocumentUseCase",),
    "domain.documents.upload": ("UploadDocumentCommand", "UploadReceipt"),
    "application.ingestion.build_document_index": ("BuildDocumentIndexUseCase",),
    "application.ingestion.run_ingestion": ("RunIngestionUseCase",),
    "application.ingestion.reindex_workspace": ("ReindexWorkspaceUseCase",),
    "application.retrieval.retrieve_context": ("RetrieveContextUseCase",),
    "domain.retrieval.models": ("RetrievalScope", "RetrievedChunk"),
    "domain.retrieval.hybrid": ("ContextBundle",),
    "application.rag.stream_chat": ("StreamRagChatUseCase",),
    "domain.rag.models": ("StreamChatCommand",),
    "domain.rag.events": (
        "RagEvent",
        "ConversationStarted",
        "CitationsResolved",
        "ClarificationRequested",
        "TokenDelta",
        "UsageReported",
        "ChatCompleted",
        "ChatFailed",
    ),
    "application.chatbots.manage_chatbot": ("ManageChatbotUseCase",),
    "application.chatbots.publish_chatbot": ("PublishChatbotUseCase",),
    "domain.chatbots.models": (
        "ChatbotConfig",
        "ChatbotRecord",
        "CreateChatbotCommand",
        "PatchChatbotCommand",
    ),
    "domain.errors": ("CoreError",),
}


def test_supported_public_api_exports() -> None:
    expected = {name for names in PUBLIC_CONTRACTS.values() for name in names}
    assert set(api.__all__) == expected
    assert len(api.__all__) == len(expected), "Duplicate public export"
    assert {name for name in vars(api) if not name.startswith("_")} == expected


@pytest.mark.parametrize(
    "module,name",
    [(module, name) for module, names in PUBLIC_CONTRACTS.items() for name in names],
)
def test_facade_preserves_contract_identity(module: str, name: str) -> None:
    implementation = importlib.import_module(f"raghub_core.{module}")
    assert getattr(api, name) is getattr(implementation, name)


def test_public_facade_imports_without_host_or_runtime_libraries() -> None:
    script = """
import importlib.abc
import sys

class BlockHost(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        forbidden = {'app', 'fastapi', 'starlette', 'sqlalchemy', 'redis', 'celery',
                     'minio', 'elasticsearch', 'httpx', 'pymupdf', 'pydantic',
                     'pydantic_settings'}
        if fullname.split('.')[0] in forbidden:
            raise AssertionError(f'Host/runtime import: {fullname}')

sys.meta_path.insert(0, BlockHost())
from raghub_core import api
assert all(hasattr(api, name) for name in api.__all__)
assert not any(name == 'app' or name.startswith('app.') for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
