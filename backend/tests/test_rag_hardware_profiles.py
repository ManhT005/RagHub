import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.task_queue.celery_app import celery_app


@pytest.mark.parametrize(
    "profile,candidates,source,top",
    [("lite_cpu", 15, 12, 5), ("standard_cpu", 25, 20, 6), ("gpu", 40, 40, 8)],
)
def test_profiles_are_opt_in_host_defaults_and_allow_explicit_overrides(
    profile, candidates, source, top
):
    settings = Settings(_env_file=None, rag_hardware_profile=profile)
    assert settings.rag_retrieval_candidates == candidates
    assert settings.rag_rerank_source_count == source and settings.rag_rerank_top_n == top
    assert not settings.rag_reranker_enabled and not settings.rag_ocr_enabled
    assert (
        Settings(
            _env_file=None, rag_hardware_profile=profile, rag_retrieval_candidates=30
        ).rag_retrieval_candidates
        == 30
    )


def test_custom_defaults_and_unknown_profiles():
    assert Settings(_env_file=None).rag_retrieval_candidates == 25
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rag_hardware_profile="unknown")


def test_celery_priority_matches_upload_recovery_reindex_policy():
    routes = celery_app.conf.task_routes
    assert (
        routes["documents.ingest_version"]["priority"]
        < celery_app.conf.task_default_priority
        < routes["providers.reindex_workspace"]["priority"]
    )
    assert celery_app.conf.broker_transport_options["priority_steps"] == [0, 1, 2, 3, 4]
