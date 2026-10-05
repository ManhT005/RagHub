"""Operations safety checks execute without Docker or installation secrets."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def ops():
    path = Path(__file__).resolve().parents[2] / "scripts" / "self-host-ops.py"
    spec = importlib.util.spec_from_file_location("selfhost_ops", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_restore_rejects_incomplete_integrity_manifest_before_docker(ops, tmp_path):
    manifest = {
        "format": 1,
        "project": "source",
        "volumes": list(ops.DATA_VOLUMES),
        "checksums": {},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    ops.model = Mock(side_effect=AssertionError("Docker must not be called"))
    with pytest.raises(ValueError, match="every required artifact"):
        ops.restore(SimpleNamespace(directory=tmp_path, project="fresh-target"))
    ops.model.assert_not_called()


def test_backup_resumes_services_when_quiescing_fails(ops, tmp_path):
    ops.model = Mock(return_value={})
    calls = []

    def compose(args, *command, **kwargs):
        calls.append(command)
        if command[0] == "ps":
            return SimpleNamespace(stdout=b"nginx\napi\nworker\n")
        if command[0] == "stop":
            raise RuntimeError("A service failed to stop")

    ops.compose = compose
    with pytest.raises(RuntimeError, match="failed to stop"):
        ops.backup(SimpleNamespace(directory=tmp_path))
    assert calls[-1] == (
        "up", "-d", "--wait", "--wait-timeout", "240", "--no-deps", "nginx", "api", "worker",
    )
