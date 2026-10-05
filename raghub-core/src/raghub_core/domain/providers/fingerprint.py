"""Embedding fingerprint v2.

v2 identifies the *semantic* embedding profile only: provider type,
normalized endpoint, model, dimension, task type and embedding options.
It deliberately excludes secrets, quota/timeout settings and config IDs,
so two credentials serving the same profile share one fingerprint and
failover never crosses models.
"""
from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit, urlunsplit

FINGERPRINT_VERSION = "v2"

# Option keys that never change the produced vectors.
_NON_SEMANTIC_OPTION_KEYS = frozenset(
    {
        "connect_timeout",
        "read_timeout",
        "max_attempts",
        "backoff_seconds",
        "retry",
        "retries",
        "quota",
        "rpm",
        "tpm",
        "rpd",
    }
)


def normalize_endpoint(base_url: str | None) -> str:
    """Normalize an endpoint for fingerprinting (scheme/host case, ports, slash)."""
    if not base_url:
        return ""
    parts = urlsplit(base_url.strip())
    scheme = parts.scheme.lower()
    host = parts.hostname.lower() if parts.hostname else ""
    port = parts.port
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    netloc = f"{host}:{port}" if port else host
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def _is_non_semantic(key: str) -> bool:
    lowered = key.lower()
    if lowered in _NON_SEMANTIC_OPTION_KEYS:
        return True
    return any(
        token in lowered
        for token in ("secret", "api_key", "apikey", "quota", "timeout", "token_limit")
    )


def semantic_options(options: dict | None) -> dict:
    """Strip non-semantic keys (secret/quota/timeout) from embedding options."""
    if not options:
        return {}
    return {key: value for key, value in options.items() if not _is_non_semantic(key)}


def embedding_fingerprint_v2(
    *,
    provider_type: str,
    base_url: str | None,
    model: str,
    dimension: int | None,
    task_type: str | None = None,
    embedding_options: dict | None = None,
) -> str:
    canonical = {
        "version": FINGERPRINT_VERSION,
        "provider_type": str(provider_type),
        "endpoint": normalize_endpoint(base_url),
        "model": model.strip() if isinstance(model, str) else model,
        "dimension": dimension,
        "task_type": task_type,
        "embedding_options": semantic_options(embedding_options),
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def quota_scope(*, provider_type: str, model: str, project: str | None = None) -> str:
    """Quota scope shared by credentials billed to the same project/account.

    Multiple Gemini keys inside one Google project share one quota bucket,
    so they must never be counted as independent capacity.
    """
    return ":".join(
        [str(provider_type), str(model), (project or "default").strip().lower() or "default"]
    )
