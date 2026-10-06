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
    indexer.dimension = 1
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


@pytest.mark.parametrize(
    "response",
    [
        {"failures": [{"cause": "unavailable"}]},
        {"timed_out": True},
        {"version_conflicts": 1},
    ],
)
def test_publication_rejects_partial_update_or_timeout(response):
    indexer = object.__new__(ChunkIndexer)
    indexer.index_name = "index"
    indexer.ensure_index = Mock()
    indexer.client = SimpleNamespace(update_by_query=Mock(return_value=response))
    with pytest.raises(ValueError, match="publication"):
        indexer.set_version_retrievable(uuid4(), retrievable=True)


@pytest.mark.parametrize("vector", [[1.0], [float("nan"), 0.0]])
def test_invalid_vectors_are_rejected_before_existing_data_is_deleted(vector):
    indexer = object.__new__(ChunkIndexer)
    indexer.dimension = 2
    indexer.ensure_index = Mock()
    indexer.client = SimpleNamespace(delete_by_query=Mock())
    chunk = TextChunk(uuid4(), 0, "raw", 1, "a.txt", None, None, "hash")
    with pytest.raises(ValueError, match="dimension"):
        indexer.replace_document_version(
            organization_id=uuid4(),
            workspace_id=uuid4(),
            document_id=uuid4(),
            document_version_id=uuid4(),
            source_name="a.txt",
            chunks=[chunk],
            embeddings={str(chunk.chunk_id): vector},
        )
    indexer.client.delete_by_query.assert_not_called()


def test_raw_citation_round_trip_preserves_normalized_search_and_metadata():
    from app.infrastructure.retrieval_mapping import chunk_from_hit, chunk_to_hit

    hit = {
        "document_id": uuid4(),
        "document_version_id": uuid4(),
        "chunk_id": uuid4(),
        "content": "Normalized fact.",
        "raw_content": "Normalized  fact.",
        "source_name": "g.pdf",
        "page_number": 3,
        "heading": "Topic",
        "score": 0.5,
        "heading_path": ["Guide", "Topic"],
        "parent_section_id": uuid4(),
        "metadata": {"row_start": 2},
    }
    chunk = chunk_from_hit(hit)
    assert chunk.content == "Normalized  fact."
    assert chunk.normalized_content == "Normalized fact."
    assert chunk_from_hit(chunk_to_hit(chunk)) == chunk
