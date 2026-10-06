from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from raghub_core.api import BuildDocumentIndexUseCase, RetrievalScope
from raghub_core.domain.ingestion.errors import IngestionError
from raghub_core.domain.ingestion.models import IngestionDocument
from raghub_core.domain.ingestion.parser import ParsedSection


async def test_oversized_text_is_rejected_before_chunking_or_provider_resolution():
    chunker, resolve = Mock(), AsyncMock()
    storage = type("Storage", (), {"get": AsyncMock(return_value=b"source")})()
    builder = BuildDocumentIndexUseCase(
        storage, lambda data, name: [ParsedSection("word " * 100000, name, 0)], chunker=chunker
    )
    document = IngestionDocument(
        RetrievalScope(uuid4(), uuid4()), uuid4(), uuid4(), "key", "source.txt"
    )
    with pytest.raises(IngestionError) as error:
        await builder.execute(document, resolve, Mock())
    assert error.value.code == "DOCUMENT_LIMIT_EXCEEDED"
    chunker.assert_not_called()
    resolve.assert_not_awaited()
