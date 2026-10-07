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
    assert settings.rag_worker_concurrency == (2 if profile == "gpu" else 1)
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


def test_empty_string_from_compose_does_not_override_preset():
    # Compose passes ${VAR:-} which resolves to empty string if unset.
    # Empty strings must be ignored in favor of the chosen hardware preset.
    settings = Settings(
        _env_file=None,
        rag_hardware_profile="gpu",
        rag_worker_concurrency="",  # type: ignore[arg-type]
        rag_retrieval_candidates="",  # type: ignore[arg-type]
    )
    assert settings.rag_worker_concurrency == 2
    assert settings.rag_retrieval_candidates == 40
    assert settings.provider_pool_max_active_jobs_per_workspace == 2


def test_explicit_env_overrides_preset():
    settings = Settings(
        _env_file=None,
        rag_hardware_profile="gpu",
        rag_worker_concurrency=1,
        rag_retrieval_candidates=50,
    )
    assert settings.rag_worker_concurrency == 1
    assert settings.rag_retrieval_candidates == 50


def test_celery_queue_isolation_and_priorities():
    routes = celery_app.conf.task_routes
    assert routes["documents.ingest_version"]["queue"] == "rag-ingestion"
    assert routes["embedding.process_work_item_batch"]["queue"] == "rag-embedding"
    assert routes["providers.reindex_workspace"]["queue"] == "rag-reindex"
    # Long-running provider tasks must route to rag-provider, NOT celery or ingestion queues
    assert routes["providers.bootstrap_health"]["queue"] == "rag-provider"
    assert routes["providers.local_download"]["queue"] == "rag-provider"
    assert routes["providers.ollama_pull"]["queue"] == "rag-provider"

    assert (
        routes["documents.ingest_version"]["priority"]
        < celery_app.conf.task_default_priority
        < routes["providers.reindex_workspace"]["priority"]
        <= routes["providers.local_download"]["priority"]
    )
    assert celery_app.conf.broker_transport_options["priority_steps"] == [0, 1, 2, 3, 4, 6, 9]
