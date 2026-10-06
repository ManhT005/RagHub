"""Download-only host scaffold. Model loading remains owned by the local runtime."""

import asyncio
import json
import os
import shutil
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.modules.ai_providers.local_catalog import ALLOWED_FILES, LOCAL_MODELS, local_spec
from app.modules.ai_providers.local_models import LocalModelDownload
from app.modules.organizations.models import Organization

ACTIVE = {"QUEUED", "DOWNLOADING", "VERIFYING"}


def download_manifest(spec):
    from huggingface_hub import HfApi

    info = HfApi(endpoint="https://huggingface.co", token=False).model_info(
        spec.repo, revision=spec.revision, files_metadata=True
    )
    files = [(row.rfilename, row.size) for row in info.siblings if row.rfilename in ALLOWED_FILES]
    if (
        info.sha != spec.revision
        or not files
        or not any(name == "model.safetensors" for name, _ in files)
        or any(type(size) is not int or size < 0 for _, size in files)
        or sum(size for _, size in files) > spec.max_bytes
    ):
        raise AppError(
            "LOCAL_MODEL_MANIFEST_INVALID", "Model manifest is invalid.", status_code=422
        )
    return files


def download_file(spec, name, target):
    from huggingface_hub import hf_hub_download

    return hf_hub_download(
        spec.repo,
        filename=name,
        revision=spec.revision,
        local_dir=target,
        endpoint="https://huggingface.co",
        token=False,
    )


def finish_snapshot(staging, final, spec, files):
    for name, size in files:
        if (staging / name).stat().st_size != size:
            raise AppError(
                "LOCAL_MODEL_VERIFY_FAILED", "Downloaded file size is invalid.", status_code=422
            )
    (staging / "raghub-manifest.json").write_text(
        json.dumps({"repo": spec.repo, "revision": spec.revision, "files": files}), encoding="utf-8"
    )
    os.replace(staging, final)


def installed_snapshot(final, spec):
    try:
        manifest = json.loads((final / "raghub-manifest.json").read_text(encoding="utf-8"))
        files = manifest["files"]
        return (
            manifest["repo"] == spec.repo
            and manifest["revision"] == spec.revision
            and any(name == "model.safetensors" for name, _ in files)
            and all(
                name in ALLOWED_FILES and (final / name).stat().st_size == size
                for name, size in files
            )
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


class LocalModelManager:
    def __init__(self, session):
        self.session = session

    async def catalog(self, organization_id):
        rows = list(
            await self.session.scalars(
                select(LocalModelDownload).where(
                    LocalModelDownload.organization_id == organization_id
                )
            )
        )
        for row in rows:
            if row.status in ACTIVE and row.updated_at < datetime.now(UTC) - timedelta(minutes=90):
                row.status, row.error_code = "FAILED", "LOCAL_DOWNLOAD_INTERRUPTED"
        await self.session.commit()
        states = {row.catalog_id: row for row in rows}
        return [
            {
                **asdict(spec),
                "docs_url": "https://huggingface.co/" + spec.repo,
                "status": states[spec.id].status if spec.id in states else "AVAILABLE",
                "completed_bytes": states[spec.id].completed_bytes if spec.id in states else 0,
                "total_bytes": states[spec.id].total_bytes if spec.id in states else 0,
                "error_code": states[spec.id].error_code if spec.id in states else None,
            }
            for spec in LOCAL_MODELS
        ]

    async def start(self, organization_id, catalog_id):
        if not get_settings().local_ai_download_enabled:
            raise AppError(
                "LOCAL_DOWNLOAD_DISABLED", "Local model downloads are disabled.", status_code=409
            )
        spec = local_spec(catalog_id)
        org = await self.session.scalar(
            select(Organization).where(Organization.id == organization_id).with_for_update()
        )
        if org is None:
            raise AppError("ORGANIZATION_NOT_FOUND", "Organization not found.", status_code=404)
        active = await self.session.scalar(
            select(LocalModelDownload).where(
                LocalModelDownload.organization_id == organization_id,
                LocalModelDownload.status.in_(ACTIVE),
            )
        )
        if active:
            raise AppError(
                "LOCAL_DOWNLOAD_IN_PROGRESS", "Wait for the active download.", status_code=409
            )
        row = await self.session.scalar(
            select(LocalModelDownload).where(
                LocalModelDownload.organization_id == organization_id,
                LocalModelDownload.catalog_id == spec.id,
            )
        )
        if row and row.status == "INSTALLED":
            return {"status": "INSTALLED"}
        if row is None:
            row = LocalModelDownload(
                organization_id=organization_id, catalog_id=spec.id, revision=spec.revision
            )
            self.session.add(row)
        row.status, row.error_code = "QUEUED", None
        row.completed_bytes, row.total_bytes = 0, 0
        await self.session.commit()
        try:
            from app.infrastructure.task_queue.celery_app import celery_app

            celery_app.send_task("providers.local_download", args=[str(row.id)])
        except Exception as exc:
            row.status, row.error_code = "FAILED", "LOCAL_DOWNLOAD_QUEUE_UNAVAILABLE"
            await self.session.commit()
            raise AppError(
                row.error_code, "Download could not be queued.", status_code=503
            ) from exc
        return {"status": row.status}

    async def run(self, job_id):
        row = await self.session.scalar(
            select(LocalModelDownload).where(LocalModelDownload.id == job_id).with_for_update()
        )
        if row is None or row.status != "QUEUED":
            return
        row.status = "DOWNLOADING"
        await self.session.commit()
        try:
            spec = local_spec(row.catalog_id)
            if row.revision != spec.revision:
                raise AppError(
                    "LOCAL_MODEL_REVISION_CHANGED",
                    "Retry with the current catalog.",
                    status_code=409,
                )
            root = Path(get_settings().local_ai_model_dir).resolve()
            parent = root / str(row.organization_id) / spec.id
            if not parent.resolve().is_relative_to(root):
                raise AppError(
                    "LOCAL_MODEL_PATH_REJECTED", "Model path is invalid.", status_code=422
                )
            parent.mkdir(parents=True, exist_ok=True)
            final, staging = parent / spec.revision, parent / (spec.revision + ".partial")
            # All path components are server-owned IDs; never accept a path or repo from the client.
            if not final.resolve().is_relative_to(root) or not staging.resolve().is_relative_to(
                root
            ):
                raise AppError(
                    "LOCAL_MODEL_PATH_REJECTED", "Model path is invalid.", status_code=422
                )
            if final.exists():
                if await asyncio.to_thread(installed_snapshot, final, spec):
                    row.status, row.error_code = "INSTALLED", None
                    await self.session.commit()
                    return
                raise AppError(
                    "LOCAL_MODEL_VERIFY_FAILED", "Snapshot verification failed.", status_code=409
                )
            files = await asyncio.to_thread(download_manifest, spec)
            row.total_bytes = sum(size for _, size in files)
            if shutil.disk_usage(parent).free < row.total_bytes + 50_000_000:
                raise AppError("LOCAL_MODEL_DISK_FULL", "Insufficient disk space.", status_code=409)
            await self.session.commit()
            staging.mkdir(exist_ok=True)
            for name, size in files:
                await asyncio.to_thread(download_file, spec, name, str(staging))
                row.completed_bytes += size
                await self.session.commit()
            row.status = "VERIFYING"
            await self.session.commit()
            await asyncio.to_thread(finish_snapshot, staging, final, spec, files)
            row.status, row.error_code = "INSTALLED", None
        except Exception as exc:
            row.status = "FAILED"
            row.error_code = (
                exc.code
                if isinstance(exc, AppError)
                else (
                    "LOCAL_DOWNLOAD_DEPENDENCY_MISSING"
                    if isinstance(exc, ImportError)
                    else "LOCAL_DOWNLOAD_FAILED"
                )
            )
        await self.session.commit()
