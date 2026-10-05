"""Retrieval explainability and Elasticsearch v2 mapping (offline)."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from raghub_core.domain.retrieval.hybrid import (
    MAPPING_VERSION,
    RETRIEVAL_CANDIDATES,
    fuse_rrf,
    fuse_rrf_with_details,
    normalize_query,
    resolve_candidate_count,
)
from raghub_core.domain.retrieval.models import RetrievedChunk

from app.infrastructure.elasticsearch.chunks import (
    bm25_query,
    chunk_index_mapping,
    knn_query,
)
from app.infrastructure.elasticsearch.reindex import (
    activate_index_version,
    rollback_index_version,
    validate_candidate_index,
    versioned_index_name,
)
from app.infrastructure.retrieval_mapping import fuse_branches_to_candidates


def _hit(name: str, score: float = 1.0) -> RetrievedChunk:
    uid = uuid4()
    return RetrievedChunk(uid, uuid4(), uid, f"content {name}", "src.md", None, None, score)


def test_normalize_query_keeps_vietnamese_diacritics():
    assert normalize_query("  tuyển   sinh  Hà Nội ") == "tuyển sinh Hà Nội"
    assert normalize_query("e\u0301") == "é"


def test_candidate_count_window():
    assert RETRIEVAL_CANDIDATES == 25
    assert resolve_candidate_count(None) == 25
    assert resolve_candidate_count(10) == 10
    assert resolve_candidate_count(100) == 100
    with pytest.raises(ValueError):
        resolve_candidate_count(9)
    with pytest.raises(ValueError):
        resolve_candidate_count(101)


def test_fuse_details_carry_branch_scores_and_presence():
    shared_bm25 = _hit("shared", 3.0)
    only_bm25 = _hit("lex", 2.0)
    shared_vec = _hit("shared", 0.9)
    shared_vec = RetrievedChunk(
        shared_bm25.document_id,
        shared_bm25.document_version_id,
        shared_bm25.chunk_id,
        shared_bm25.content,
        shared_bm25.source_name,
        None,
        None,
        0.9,
    )
    only_vec = _hit("vec", 0.8)
    details = fuse_rrf_with_details([[shared_bm25, only_bm25], [shared_vec, only_vec]], limit=5)
    by_content = {c.chunk.content: c for c in details}
    shared = by_content["content shared"]
    assert shared.fused_rank == 1
    assert shared.bm25_rank == 1 and shared.vector_rank == 1
    assert shared.bm25_score == 3.0 and shared.vector_score == 0.9
    assert shared.in_bm25 and shared.in_vector
    assert by_content["content lex"].in_bm25 and not by_content["content lex"].in_vector
    assert by_content["content vec"].in_vector and not by_content["content vec"].in_bm25
    # Public shape unchanged: same order, fused score on the chunk.
    plain = fuse_rrf([[shared_bm25, only_bm25], [shared_vec, only_vec]], limit=5)
    assert [h.content for h in plain] == [c.chunk.content for c in details]


def test_mapping_v2_has_folded_and_retrievable():
    assert MAPPING_VERSION == "vi_hybrid_v2"
    mapping = chunk_index_mapping(768)
    props = mapping["mappings"]["properties"]
    assert props["content"]["fields"]["folded"] == {"type": "text", "analyzer": "vi_folded"}
    assert mapping["settings"]["analysis"]["analyzer"]["vi_folded"]["filter"] == [
        "lowercase",
        "asciifolding",
    ]
    assert props["retrievable"] == {"type": "boolean"}
    assert props["mapping_version"] == {"type": "keyword"}
    assert mapping["mappings"]["properties"]["embedding"]["dims"] == 768


def test_bm25_query_boosts_and_pre_cutoff_filters():
    org, ws = uuid4(), uuid4()
    query = bm25_query("tuyển sinh", org, ws)
    fields = query["bool"]["must"][0]["multi_match"]["fields"]
    assert "content^1.0" in fields
    assert "content.folded^0.8" in fields  # exact Vietnamese outranks folded
    assert "heading.text^2.0" in fields
    assert "source_name.text^1.2" in fields
    filters = query["bool"]["filter"]
    assert {"term": {"organization_id": str(org)}} in filters
    assert {"term": {"workspace_id": str(ws)}} in filters
    assert {"term": {"retrievable": True}} in filters


def test_knn_query_filters_before_cutoff():
    org, ws = uuid4(), uuid4()
    query = knn_query([0.1, 0.2], org, ws, k=25, num_candidates=100)
    assert query["knn"]["k"] == 25 and query["knn"]["num_candidates"] == 100
    assert {"term": {"retrievable": True}} in query["knn"]["filter"]
    assert {"term": {"workspace_id": str(ws)}} in query["knn"]["filter"]


def test_fuse_branches_to_candidates():
    uid = str(uuid4())

    def raw(name, score):
        return {
            "document_id": uid,
            "document_version_id": str(uuid4()),
            "chunk_id": uid,
            "content": name,
            "source_name": "s",
            "page_number": None,
            "heading": None,
            "score": score,
        }

    candidates = fuse_branches_to_candidates([raw("a", 5.0)], [raw("a", 0.7)], limit=5)
    assert len(candidates) == 1
    assert candidates[0].bm25_score == 5.0 and candidates[0].vector_score == 0.7


def test_versioned_index_name_and_validation():
    assert versioned_index_name("raghub_chunks_x", "vi_hybrid_v2") == "raghub_chunks_x__vihybridv2"

    class Indices:
        def __init__(self, mapping, count):
            self._mapping, self._count = mapping, count

        def exists(self, *, index):
            return True

        def get_mapping(self, *, index):
            return {"idx": self._mapping}

        def count(self, *, index):
            return {"count": self._count}

    class Client:
        def __init__(self, mapping, count):
            self.indices = Indices(mapping, count)

        def count(self, *, index):
            return {"count": self.indices._count}

    good_map = {"mappings": {"properties": {"embedding": {"dims": 768}}}}
    assert (
        validate_candidate_index(Client(good_map, 10), index_name="i", dimension=768)["ok"] is True
    )
    bad = validate_candidate_index(Client(good_map, 10), index_name="i", dimension=128)
    assert bad["ok"] is False and "dimension" in bad["reason"]
    empty = validate_candidate_index(Client(good_map, 0), index_name="i", dimension=768)
    assert empty["ok"] is False


async def test_activation_and_rollback_swap_pointers():
    from app.modules.ai_providers.models import EmbeddingIndexVersion
    from app.modules.workspaces.models import Workspace

    ws_id, old_id, new_id = uuid4(), uuid4(), uuid4()
    workspace = Workspace(id=ws_id)
    workspace.active_embedding_index_version_id = old_id
    workspace.pending_embedding_index_version_id = new_id
    old = EmbeddingIndexVersion(id=old_id)
    old.status = "ACTIVE"
    old.workspace_id = ws_id
    new = EmbeddingIndexVersion(id=new_id)
    new.workspace_id = ws_id
    new.status = "BUILDING"

    async def fake_get(model, obj_id):
        return {(Workspace, ws_id): workspace, (EmbeddingIndexVersion, old_id): old,
                (EmbeddingIndexVersion, new_id): new}[(model, obj_id)]

    session = AsyncMock()
    session.get.side_effect = fake_get
    previous = await activate_index_version(session, workspace_id=ws_id, new_version_id=new_id)
    assert previous == old_id
    assert old.status == "RETIRED" and new.status == "ACTIVE"
    assert workspace.active_embedding_index_version_id == new_id
    assert workspace.pending_embedding_index_version_id is None

    await rollback_index_version(session, workspace_id=ws_id, previous_version_id=old_id)
    assert workspace.active_embedding_index_version_id == old_id
    assert old.status == "ACTIVE" and new.status == "FAILED"


async def test_activation_rejects_foreign_version():
    from app.modules.ai_providers.models import EmbeddingIndexVersion
    from app.modules.workspaces.models import Workspace

    ws_id, new_id = uuid4(), uuid4()
    workspace = Workspace(id=ws_id)
    workspace.active_embedding_index_version_id = None
    workspace.pending_embedding_index_version_id = None
    new = EmbeddingIndexVersion(id=new_id)
    new.workspace_id = uuid4()

    async def fake_get(model, obj_id):
        return workspace if model is Workspace else new

    session = AsyncMock()
    session.get.side_effect = fake_get
    with pytest.raises(ValueError, match="another workspace"):
        await activate_index_version(session, workspace_id=ws_id, new_version_id=new_id)
