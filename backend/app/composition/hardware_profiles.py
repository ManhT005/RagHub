"""Opt-in capacity presets; these are benchmark starting points, not approved baselines.

Precedence (highest first):

1. Explicit, non-empty environment / constructor value.
2. Hardware preset selected by ``RAG_HARDWARE_PROFILE``.
3. ``Settings`` field default.

Compose files pass optional tuning variables as ``${VAR:-}``; an empty string
therefore means "not set" and must never shadow the preset.
"""

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

# Every field a preset may own. Empty values for these keys are treated as unset.
PROFILE_KEYS = frozenset(key for profile in PROFILES.values() for key in profile)


def _is_unset(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def apply_profile(values):
    if not isinstance(values, dict):
        return values
    explicit = {
        key: value
        for key, value in values.items()
        if not (str(key).lower() in PROFILE_KEYS | {"rag_hardware_profile"} and _is_unset(value))
    }
    profile = explicit.get("rag_hardware_profile")
    if isinstance(profile, str):
        profile = profile.strip().lower()
        explicit["rag_hardware_profile"] = profile
    preset = PROFILES.get(profile, {})
    present = {str(key).lower() for key in explicit}
    return {**{k: v for k, v in preset.items() if k not in present}, **explicit}
