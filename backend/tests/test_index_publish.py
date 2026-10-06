from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from raghub_core.domain.ingestion.chunker import TextChunk

from app.infrastructure.elasticsearch.chunks import ChunkIndexer


@pytest.mark.parametrize("count,bulk_failure", [(1, False), (0, False), (0, True)])
def test_index_is_published_only_after_validated_write(monkeypatch, count, bulk_failure):
    indexer = object.__new__(ChunkIndexer)
    indexer.index_name = "inactive-rebuild"
    indexer.ensure_index = Mock()
    indexer.client = SimpleNamespace(
        delete_by_query=Mock(), count=Mock(return_value={"count": count})
    )
    indexer.set_version_retrievable = Mock()
    chunk = TextChunk(uuid4(), 0, "text", 1, "a.txt", None, None, "hash")

    def bulk(client, actions, **kwargs):
        assert all(action["_source"]["retrievable"] is False for action in actions)
        indexer.set_version_retrievable.assert_not_called()
        if bulk_failure:
            raise ConnectionError("index unavailable")

    monkeypatch.setattr("app.infrastructure.elasticsearch.chunks.helpers.bulk", bulk)
    kwargs = dict(
        organization_id=uuid4(),
        workspace_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        source_name="a.txt",
        chunks=[chunk],
        embeddings={str(chunk.chunk_id): [1.0]},
    )
    if bulk_failure or count != 1:
        with pytest.raises((ConnectionError, ValueError)):
            indexer.replace_document_version(**kwargs)
        indexer.set_version_retrievable.assert_not_called()
    else:
        indexer.replace_document_version(**kwargs)
        indexer.set_version_retrievable.assert_called_once_with(
            kwargs["document_version_id"], retrievable=True
        )
