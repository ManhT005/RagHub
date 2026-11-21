"""Resolve a curated, checksum-pinned local installation without network calls."""

import asyncio
import importlib.util
import re
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.modules.ai_providers.local_catalog import LOCAL_RERANK_ID, local_spec
from app.modules.ai_providers.local_manager import installed_snapshot
from app.modules.ai_providers.local_models import LocalModelDownload


def local_dependencies_available(catalog_id=LOCAL_RERANK_ID):
    packages = (
        ("torch", "transformers")
        if catalog_id != LOCAL_RERANK_ID
        else ("torch", "sentence_transformers")
    )
    return all(importlib.util.find_spec(name) is not None for name in packages)


def installed_paths(organization_id, catalog_id=LOCAL_RERANK_ID):
    spec = local_spec(catalog_id)
    root = Path(get_settings().local_ai_model_dir).resolve()
    final = root / str(organization_id) / spec.id / spec.revision
    if not final.resolve().is_relative_to(root):
        return None
    try:
        checksum = final.with_suffix(".sha256").read_text(encoding="ascii").strip()
        if re.fullmatch(r"[0-9a-f]{64}", checksum) and installed_snapshot(final, spec):
            return str(final), checksum
    except (OSError, ValueError):
        pass
    return None


async def local_installation(session, organization_id, catalog_id=LOCAL_RERANK_ID):
    settings = get_settings()
    row = await session.scalar(
        select(LocalModelDownload).where(
            LocalModelDownload.organization_id == organization_id,
            LocalModelDownload.catalog_id == catalog_id,
        )
    )
    paths = None
    if row and row.status == "INSTALLED":
        paths = await asyncio.to_thread(installed_paths, organization_id, catalog_id)
    # Preserve an existing deployment prepared using the opt-in overlay.
    if not paths and catalog_id == LOCAL_RERANK_ID and settings.rag_reranker_enabled:
        path, checksum = settings.rag_reranker_snapshot_path, settings.rag_reranker_expected_sha256
        if path and re.fullmatch(r"[0-9a-f]{64}", checksum) and Path(path).is_dir():
            paths = path, checksum
    supported = local_dependencies_available(
        *([catalog_id] if catalog_id != LOCAL_RERANK_ID else [])
    )
    ready = bool(paths and supported and settings.ai_rerank_enabled)
    status = row.status if row else "AVAILABLE"
    if ready:
        status = "INSTALLED"
    elif not supported:
        status = "UNSUPPORTED"
    elif not settings.ai_rerank_enabled:
        status = "DISABLED"
    elif status == "INSTALLED":
        status = "FAILED"
    return {
        "catalog_id": catalog_id,
        "model": local_spec(catalog_id).repo,
        "status": status,
        "ready": ready,
        "download_enabled": settings.local_ai_download_enabled
        and supported
        and settings.ai_rerank_enabled,
        "error_code": row.error_code if row else None,
    }, paths
