"""One engine lifecycle, joined through fake ports, without any runtime dependency."""

from uuid import uuid4

from app.application.documents.upload_document import UploadDocumentUseCase
from app.application.ingestion.build_document_index import BuildDocumentIndexUseCase
from app.application.ingestion.run_ingestion import RunIngestionUseCase
from app.application.rag.stream_chat import StreamRagChatUseCase
from app.application.retrieval.retrieve_context import RetrieveContextUseCase
from app.core_domain.documents.upload import UploadDocumentCommand
from app.core_domain.ingestion.models import IngestionDocument
from app.core_domain.ingestion.parser import parse_document
from app.core_domain.rag.events import ChatCompleted, CitationsResolved
from app.core_domain.rag.models import StreamChatCommand
from app.core_domain.retrieval.models import RetrievalScope, RetrievedChunk

from .fakes import (
    FakeObjectStorage,
    FakeProviderResolver,
    FakeTaskQueue,
    FakeUploadRepository,
    FakeVectorStore,
)
from .test_ingestion import Repository
from .test_rag_runtime import Chatbots, Conversations, Usage
from .test_retrieval import Readiness


async def test_upload_ingest_index_retrieve_chat_preserves_scope_and_source():
    storage, queue, uploads = FakeObjectStorage(), FakeTaskQueue(), FakeUploadRepository()
    providers, index = FakeProviderResolver(), FakeVectorStore()
    scope = RetrievalScope(uuid4(), uuid4())
    command = UploadDocumentCommand(
        scope.organization_id,
        scope.workspace_id,
        "guide.md",
        "text/markdown",
        b"# Recovery\n\nThe recovery code is ORCHID-729.",
    )
    receipt = await UploadDocumentUseCase(uploads, storage, queue).execute(command)
    assert uploads.commits == 1 and queue.ingestion == [receipt.document_version_id]
    document = IngestionDocument(
        scope,
        receipt.document_id,
        receipt.document_version_id,
        uploads.uploads[0]["storage_key"],
        command.filename,
    )
    ingestion = Repository(document)
    await RunIngestionUseCase(
        ingestion,
        BuildDocumentIndexUseCase(storage, parse_document),
        providers,
        lambda _: index,
    ).execute(receipt.document_version_id)
    assert ingestion.stages[-1] == ("READY", 100)
    indexed = index.indexes[0]
    assert indexed.scope == scope

    class Search:
        async def search(self, requested_scope, query, vector, limit):
            if requested_scope != indexed.scope:
                return []
            return [
                RetrievedChunk(
                    indexed.document_id,
                    indexed.document_version_id,
                    item.chunk.chunk_id,
                    item.chunk.content,
                    indexed.source_name,
                    item.chunk.page_number,
                    item.chunk.heading,
                    1.0,
                )
                for item in indexed.chunks
            ][:limit]

        async def close(self):
            pass

    ready = Readiness()
    ready.ready_pairs.add((document.document_id, document.version_id))
    retrieval = RetrieveContextUseCase(providers, ready, lambda _: Search())
    assert not await retrieval.retrieve(RetrievalScope(uuid4(), uuid4()), "Recovery", 5)
    chatbots, conversations, usage = Chatbots(), Conversations(), Usage()
    from dataclasses import replace

    chatbots.config = replace(chatbots.config, scope=scope)
    events = [
        event
        async for event in StreamRagChatUseCase(
            chatbots,
            retrieval,
            providers,
            conversations,
            usage,
        ).execute(StreamChatCommand(scope.organization_id, chatbots.config.id, "Recovery code?"))
    ]
    citations = next(event for event in events if isinstance(event, CitationsResolved)).citations
    assert citations[0].document_id == receipt.document_id
    assert citations[0].chunk_id == indexed.chunks[0].chunk.chunk_id
    assert "ORCHID-729" in providers.chat.calls[0][0][0].content
    assert isinstance(events[-1], ChatCompleted)
    assert usage.records[0].scope == scope and conversations.commits == 2
