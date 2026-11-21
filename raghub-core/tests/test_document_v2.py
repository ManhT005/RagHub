from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from raghub_core.api import BuildDocumentIndexUseCase, RetrievalScope
from raghub_core.domain.ingestion.markdown_v2 import chunk_markdown_blocks
from raghub_core.domain.ingestion.models import IngestionDocument
from raghub_core.domain.ingestion.parser import ParsedBlock
from raghub_core.domain.ingestion.text_v2 import parse_text_blocks
from raghub_core.domain.ingestion.tokenizer import ENCODING
from raghub_core.ports.provider_resolver import EmbeddingRuntime

from .fakes import FakeEmbeddingProvider, FakeObjectStorage, FakeVectorStore


async def test_document_v2_uses_selected_parser_once_before_embedding():
    storage, provider, store = FakeObjectStorage(), FakeEmbeddingProvider(), FakeVectorStore()
    storage.objects["key"] = b"file bytes"
    document = IngestionDocument(
        RetrievalScope(uuid4(), uuid4()), uuid4(), uuid4(), "key", "guide.pdf"
    )
    blocks = [ParsedBlock("    print(1)\n\n    print(2)", "guide.pdf", 0, 3, type="code")]
    old = Mock(side_effect=AssertionError("legacy parser must not run"))
    parser = Mock(return_value=blocks)
    resolve = AsyncMock(
        return_value=EmbeddingRuntime(provider, "index", 2, document_pipeline="document-v2")
    )
    builder = BuildDocumentIndexUseCase(storage, old, structured_parser=parser)
    result = await builder.execute(document, resolve, lambda _: store)
    parser.assert_called_once_with(b"file bytes", "guide.pdf")
    old.assert_not_called()
    resolve.assert_awaited_once()
    assert result.chunks[0].chunk.page_number == 3
    assert "Page: 3" in provider.calls[0][0]
    assert "    print(1)\n\n    print(2)" in provider.calls[0][0]
    assert provider.calls[0][0].count("Source:") == 1


async def test_legacy_profile_keeps_legacy_parser_with_versioned_host():
    storage, provider, store = FakeObjectStorage(), FakeEmbeddingProvider(), FakeVectorStore()
    storage.objects["key"] = b"body"
    document = IngestionDocument(RetrievalScope(uuid4(), uuid4()), uuid4(), uuid4(), "key", "a.txt")
    old = Mock(return_value=parse_text_blocks(b"Original body", "a.txt"))
    new = Mock(side_effect=AssertionError("v2 parser must remain opt-in"))
    builder = BuildDocumentIndexUseCase(storage, old, structured_parser=new)
    await builder.execute(
        document, AsyncMock(return_value=EmbeddingRuntime(provider, "i", 2)), lambda _: store
    )
    old.assert_called_once()
    new.assert_not_called()


def test_document_v2_never_merges_pages_and_retains_real_spreadsheet_rows():
    blocks = [ParsedBlock("Same heading body.", "a.pdf", i, i + 1) for i in range(2)]
    chunks = chunk_markdown_blocks(blocks, uuid4(), pipeline="document-v2")
    assert [c.page_number for c in chunks] == [1, 2]
    table = ParsedBlock(
        "| A | B |\n|---|---|\n" + "\n".join(f"| item-{i} | value |" for i in range(50)),
        "a.xlsx",
        0,
        type="table",
        heading_path=("Data",),
        metadata={"sheet": "Data", "row_numbers": list(range(10, 110, 2))},
    )
    chunks = chunk_markdown_blocks([table], uuid4(), pipeline="document-v2", target_tokens=100)
    assert chunks[0].metadata["row_start"] == 10 and chunks[-1].metadata["row_end"] == 108
    assert all(len(ENCODING.encode(c.embedding_content)) <= 100 for c in chunks)
