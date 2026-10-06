from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.modules.ai_providers import local_manager
from app.modules.ai_providers.local_catalog import ALLOWED_FILES, LOCAL_MODELS, local_spec
from app.modules.ai_providers.local_manager import LocalModelManager, installed_snapshot
from app.modules.ai_providers.local_models import LocalModelDownload
from app.modules.ai_providers.models import ProviderConfig
from app.modules.organizations.models import Organization


def test_local_catalog_is_pinned_and_disallows_arbitrary_paths_repos_or_code():
    assert all(len(spec.revision) == 40 for spec in LOCAL_MODELS)
    assert not any(name.endswith((".py", ".bin", ".pkl")) for name in ALLOWED_FILES)
    for model in ["../outside", "some/private-repo", "https://host/model"]:
        with pytest.raises(AppError):
            local_spec(model)


async def test_download_is_scoped_async_idempotent_and_does_not_register_runtime(
    isolated_sessions, tmp_path, monkeypatch
):
    from app.infrastructure.task_queue.celery_app import celery_app

    calls = []
    monkeypatch.setattr(
        celery_app, "send_task", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    monkeypatch.setattr(
        local_manager,
        "get_settings",
        lambda: SimpleNamespace(local_ai_download_enabled=True, local_ai_model_dir=str(tmp_path)),
    )
    monkeypatch.setattr(
        local_manager, "download_manifest", lambda _: [("config.json", 2), ("model.safetensors", 4)]
    )

    def download(spec, name, target):
        assert spec.revision == LOCAL_MODELS[0].revision
        Path(target, name).write_bytes(b"{}" if name == "config.json" else b"safe")

    monkeypatch.setattr(local_manager, "download_file", download)
    async with isolated_sessions() as session:
        first, other = (
            Organization(name="first", slug=uuid4().hex),
            Organization(name="other", slug=uuid4().hex),
        )
        session.add_all([first, other])
        await session.commit()
        manager = LocalModelManager(session)
        assert await manager.start(first.id, "minilm-l6") == {"status": "QUEUED"}
        with pytest.raises(AppError) as error:
            await manager.start(first.id, "multilingual-minilm")
        assert error.value.code == "LOCAL_DOWNLOAD_IN_PROGRESS"
        row = await session.scalar(select(LocalModelDownload))
        await manager.run(row.id)
        assert row.status == "INSTALLED" and row.completed_bytes == row.total_bytes == 6
        snapshot = tmp_path / str(first.id) / "minilm-l6" / LOCAL_MODELS[0].revision
        assert installed_snapshot(snapshot, LOCAL_MODELS[0])
        assert not snapshot.with_name(snapshot.name + ".partial").exists()
        assert await manager.start(first.id, "minilm-l6") == {"status": "INSTALLED"}
        assert len(calls) == 1
        assert (await manager.catalog(other.id))[0]["status"] == "AVAILABLE"
        assert await session.scalar(select(func.count()).select_from(ProviderConfig)) == 0


async def test_failed_download_never_exposes_private_upstream_error(
    isolated_sessions, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        local_manager, "get_settings", lambda: SimpleNamespace(local_ai_model_dir=str(tmp_path))
    )

    def fail(_):
        raise ConnectionError("private upstream token and filesystem details")

    monkeypatch.setattr(local_manager, "download_manifest", fail)
    async with isolated_sessions() as session:
        org = Organization(name="test", slug=uuid4().hex)
        session.add(org)
        await session.flush()
        row = LocalModelDownload(
            organization_id=org.id,
            catalog_id="minilm-l6",
            revision=LOCAL_MODELS[0].revision,
            status="QUEUED",
        )
        session.add(row)
        await session.commit()
        await LocalModelManager(session).run(row.id)
        assert row.status == "FAILED" and row.error_code == "LOCAL_DOWNLOAD_FAILED"
