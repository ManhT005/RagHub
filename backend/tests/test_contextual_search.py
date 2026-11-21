from uuid import uuid4

from app.infrastructure.elasticsearch.chunks import bm25_query, chunk_index_mapping


def test_context_fields_are_searchable_without_opening_arbitrary_metadata():
    props = chunk_index_mapping(384)["mappings"]["properties"]
    assert props["metadata"]["enabled"] is False
    assert props["source_title"]["analyzer"] == "vi_folded"
    assert props["fact_years"]["type"] == "integer"
    assert props["entity_codes"]["type"] == "keyword"


def test_query_preferences_never_become_hard_filters_or_change_scope():
    org, ws = uuid4(), uuid4()
    query = bm25_query("điểm chuẩn ngành 7480201 năm 2025", org, ws)["bool"]
    assert query["filter"] == [
        {"term": {"organization_id": str(org)}},
        {"term": {"workspace_id": str(ws)}},
        {"term": {"retrievable": True}},
    ]
    assert {"term": {"fact_years": {"value": 2025, "boost": 3.0}}} in query["should"]
    assert {"term": {"entity_codes": {"value": "7480201", "boost": 4.0}}} in query["should"]
    assert "table_headers^1.5" in query["must"][0]["multi_match"]["fields"]


def test_undated_question_keeps_lexical_search_without_date_constraints():
    preferences = bm25_query("thủ tục nhập học", uuid4(), uuid4())["bool"]["should"]
    assert len(preferences) == 1
    assert preferences[0]["multi_match"]["operator"] == "and"


def test_context_version_invalidates_previous_relevance_calibration(monkeypatch):
    from app.modules.search import relevance

    args = dict(candidates=30, rrf_k=60, mapping_version="vi_hybrid_v2")
    current = relevance.retrieval_config_hash(**args)
    monkeypatch.setattr(relevance, "CONTEXT_VERSION", "older-context")
    assert relevance.retrieval_config_hash(**args) != current


def test_topic_preference_uses_body_and_table_context_not_filename_year():
    preferences = bm25_query("cho tôi biết học phí năm 2025 là bao nhiêu", uuid4(), uuid4())[
        "bool"
    ]["should"]
    topic = preferences[0]["multi_match"]
    assert topic["query"] == "hoc phi"
    assert "source_title" not in topic["fields"]
