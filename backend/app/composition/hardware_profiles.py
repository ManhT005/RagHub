"""Opt-in capacity presets; these are benchmark starting points, not approved baselines."""

PROFILES = {
    "lite_cpu": {
        "rag_worker_concurrency": 1,
        "rag_retrieval_candidates": 15,
        "rag_rerank_source_count": 12,
        "rag_rerank_top_n": 5,
        "rag_reranker_enabled": False,
        "provider_pool_max_active_jobs_per_workspace": 1,
    },
    "standard_cpu": {
        "rag_worker_concurrency": 1,
        "rag_retrieval_candidates": 25,
        "rag_rerank_source_count": 20,
        "rag_rerank_top_n": 6,
        "rag_adaptive_rerank_enabled": True,
        "provider_pool_max_active_jobs_per_workspace": 1,
    },
    "gpu": {
        "rag_worker_concurrency": 2,
        "rag_retrieval_candidates": 40,
        "rag_rerank_source_count": 40,
        "rag_rerank_top_n": 8,
        "rag_adaptive_rerank_enabled": True,
        "provider_pool_max_active_jobs_per_workspace": 2,
    },
}


def apply_profile(values):
    if not isinstance(values, dict):
        return values
    return {**PROFILES.get(values.get("rag_hardware_profile"), {}), **values}
