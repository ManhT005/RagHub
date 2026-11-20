"""Deployment checks are offline; never operate on the actual Docker daemon."""

import hashlib
import importlib.util
import io
import json
import tarfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def deployer():
    path = Path(__file__).resolve().parents[2] / "scripts/deploy-develop.py"
    spec = importlib.util.spec_from_file_location("deploy_develop", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def model():
    names = (
        "api",
        "worker",
        "worker-provider",
        "worker-ocr",
        "nginx",
        "admin-web",
        "chat-widget",
        "widget-demo",
        "migrate",
        "postgres",
        "redis",
        "elasticsearch",
        "minio",
    )
    return {
        "services": {
            name: {
                "image": name + ":pinned",
                "environment": {
                    "APP_SECRET_KEY": "secret",
                    "PROVIDER_MASTER_KEY": "encrypted-key",
                },
            }
            for name in names
        },
        "volumes": {
            key: {"name": "existing_" + key}
            for key in ("postgres-data", "redis-data", "elasticsearch-data", "minio-data")
        },
    }


@pytest.mark.parametrize("change", ["volume", "storage", "secret", "reranking"])
def test_identity_changes_fail_before_deployment(deployer, change):
    old, new = model(), model()
    if change == "volume":
        new["volumes"]["postgres-data"]["name"] = "empty_new_database"
    elif change == "storage":
        new["services"]["postgres"]["image"] = "postgres:new"
    elif change == "secret":
        new["services"]["api"]["environment"]["PROVIDER_MASTER_KEY"] = "different"
    else:
        old["services"]["api"]["environment"]["RAG_RERANKER_ENABLED"] = "true"
    with pytest.raises(ValueError):
        deployer.verify_layout(old, new)


@pytest.mark.parametrize("name,symlink", [("../escaped", False), ("link", True)])
def test_release_archive_cannot_escape(deployer, tmp_path, name, symlink):
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo(name)
        if symlink:
            info.type, info.linkname = tarfile.SYMTYPE, "/etc"
        tar.addfile(info)
    with pytest.raises(ValueError):
        deployer.extract_release(archive, tmp_path / "release")
    assert not (tmp_path / "escaped").exists()


def test_backup_failure_restarts_all_prior_services_including_ocr(deployer, tmp_path):
    stack = Mock()
    stack.call.side_effect = RuntimeError("stop failed")
    active = ["api", "worker", "worker-ocr", "postgres", "redis", "elasticsearch", "minio"]
    with pytest.raises(RuntimeError):
        deployer.backup(stack, model(), tmp_path / "env", tmp_path / "backup", active)
    assert "worker-ocr" in stack.call.call_args_list[0].args
    assert stack.call.call_args_list[-1].args == (
        "start",
        "--wait",
        "--wait-timeout",
        "240",
        *active,
    )


def test_backup_is_restore_compatible_and_pins_prior_registry_tag(deployer, tmp_path, monkeypatch):
    source_env = tmp_path / "runtime.env"
    source_env.write_text("APP_SECRET_KEY=keep\nRAGHUB_IMAGE_TAG=develop\n")
    directory = tmp_path / "backup"
    calls = []

    def compose(*args, output=None):
        calls.append(args)
        if output:
            output.write(b"database dump")
        return b""

    def helper(image, path, command, volume=None):
        if volume:
            key = next(key for key in deployer.ARCHIVES if key in command)
            (path / (key + ".tar")).write_bytes(b"archive")
        if command.startswith("cd /backup; sha256sum ") and "-c" not in command:
            names = ["postgres.dump", "runtime.env", *[key + ".tar" for key in deployer.ARCHIVES]]
            return "".join(
                hashlib.sha256((path / name).read_bytes()).hexdigest() + "  " + name + "\n"
                for name in names
            ).encode()
        return b""

    monkeypatch.setattr(deployer, "helper", helper)
    stack = SimpleNamespace(project="existing", image_tag="sha-" + "a" * 40, call=compose)
    active = ["api", "worker-ocr", *deployer.STORAGE]
    deployer.backup(stack, model(), source_env, directory, active)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["project"] == "existing" and manifest["format"] == 1
    assert set(manifest["checksums"]) == {
        "postgres.dump",
        "runtime.env",
        *[key + ".tar" for key in deployer.ARCHIVES],
    }
    assert "RAGHUB_IMAGE_TAG=sha-" in (directory / "runtime.env").read_text()
    assert source_env.read_text().endswith("RAGHUB_IMAGE_TAG=develop\n")
    assert "api" not in calls[-1] and "worker-ocr" in calls[0]


@pytest.mark.parametrize("failure", [None, "migration", "health"])
def test_deploy_order_and_no_unsafe_rollback(deployer, tmp_path, monkeypatch, failure):
    sha = "a" * 40
    area = tmp_path / ".deploy"
    area.mkdir()
    (area / "config.json").write_text(
        json.dumps(
            {
                "project": "raghub-selfhost",
                "initial_compose_files": ["old.yml"],
            }
        )
    )
    (tmp_path / ".env.self-host").write_text("secret=preserve\n")
    events = []
    active = ["api", "worker", "worker-ocr", "nginx", *deployer.STORAGE]

    class FakeStack:
        def __init__(self, root, project, env_file, files, image_tag=None):
            self.target = image_tag is not None

        def model(self):
            return deepcopy(model())

        def call(self, *args, **kwargs):
            if args[:2] == ("ps", "--services"):
                return "\n".join(active).encode()
            if args == ("ps", "-q"):
                return b""
            events.append(("target" if self.target else "source", args))
            if args[0] == "run" and failure == "migration":
                raise RuntimeError("migration failed")
            return b""

    monkeypatch.setattr(deployer, "Stack", FakeStack)
    monkeypatch.setattr(
        deployer, "extract_release", lambda archive, destination: destination.mkdir()
    )
    monkeypatch.setattr(
        deployer,
        "run",
        lambda command, **kw: json.dumps(
            [{"Config": {"Labels": {"org.opencontainers.image.revision": sha}}}]
        ).encode(),
    )
    monkeypatch.setattr(deployer, "backup", lambda *args: events.append(("backup", ())))

    class Response:
        status = 200

        def __enter__(self):
            if failure == "health":
                raise RuntimeError("readiness failed")
            return io.StringIO('{"status":"ok"}')

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(deployer.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    args = SimpleNamespace(root=tmp_path, sha=sha, archive="trusted.tar")
    # json.load uses the object returned by the context manager, so set its status.
    if failure is None:
        response = io.StringIO('{"status":"ok"}')
        response.status = 200
        monkeypatch.setattr(deployer.urllib.request, "urlopen", lambda *a, **kw: response)
        deployer.deploy(args)
        assert json.loads((area / "state.json").read_text())["tag"] == "sha-" + sha
    else:
        with pytest.raises(RuntimeError):
            deployer.deploy(args)
        assert not (area / "state.json").exists()
        assert json.loads((area / "last-attempt.json").read_text())["phase"] == failure
        assert any(item[1][0] == "stop" for item in events if item[0] == "target")
        assert not any(item[0] == "source" and item[1][0] in {"up", "start"} for item in events)
    labels = [item[0] if item[0] == "backup" else item[1][0] for item in events]
    assert labels.index("pull") < labels.index("backup") < labels.index("run")
    assert (tmp_path / ".env.self-host").read_text() == "secret=preserve\n"


def test_next_deployment_uses_state_tag_not_mutable_env(deployer, tmp_path, monkeypatch):
    area = tmp_path / ".deploy"
    area.mkdir()
    (area / "config.json").write_text(json.dumps({"project": "raghub-selfhost"}))
    (area / "state.json").write_text(
        json.dumps(
            {
                "sha": "a" * 40,
                "tag": "sha-" + "a" * 40,
                "release": str(tmp_path / "prior"),
                "files": ["runtime.yml"],
            }
        )
    )
    calls = []

    def stack(*args):
        calls.append(args)
        raise RuntimeError("stop after source construction")

    monkeypatch.setattr(deployer, "Stack", stack)
    with pytest.raises(RuntimeError):
        deployer.deploy(SimpleNamespace(root=tmp_path, sha="b" * 40))
    assert calls[0][-1] == "sha-" + "a" * 40
