import ast
import subprocess
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
LAYERS = {
    "domain": (APP.parent / "raghub_core" / "domain", "raghub_core.domain"),
    "ports": (APP.parent / "raghub_core" / "ports", "raghub_core.ports"),
    "application": (APP.parent / "raghub_core" / "application", "raghub_core.application"),
}
FORBIDDEN = {
    "fastapi",
    "starlette",
    "celery",
    "redis",
    "minio",
    "elasticsearch",
    "sqlalchemy",
    "httpx",
    "pymupdf",
    "pydantic",
    "pydantic_settings",
}


def forbidden_imports(source: str, *, layer: str) -> list[str]:
    violations = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                violations.append("relative import obscures boundary")
            names = [node.module or ""]
        for name in names:
            if name.split(".")[0] in FORBIDDEN:
                violations.append(name)
            root = name.split(".")[0]
            approved = {"tiktoken"} if layer == "domain" else set()
            if (
                root not in {"app", "raghub_core"}
                and root not in sys.stdlib_module_names | approved
            ):
                violations.append(name)
            if root in {"app", "raghub_core"}:
                allowed = [LAYERS["domain"][1]]
                if layer == "application":
                    allowed.extend([LAYERS["ports"][1], LAYERS["application"][1]])
                if not any(name == value or name.startswith(value + ".") for value in allowed):
                    violations.append(name)
    return violations


def test_engine_dependency_direction() -> None:
    violations = []
    for layer, (directory, _) in LAYERS.items():
        assert directory.is_dir(), f"Missing engine layer: {layer}"
        for file in directory.rglob("*.py"):
            for name in forbidden_imports(file.read_text(encoding="utf-8"), layer=layer):
                violations.append(f"{file.relative_to(APP.parent)}: {name}")
    assert not violations, "\n".join(violations)


def test_services_do_not_depend_on_delivery() -> None:
    violations = []
    for file in (APP / "modules").rglob("service.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if any(name.startswith("app.delivery") for name in names):
                violations.append(str(file.relative_to(APP)))
    assert not violations, "\n".join(violations)


def test_engine_errors_have_no_http_status_semantics() -> None:
    from raghub_core.domain.errors import CoreError
    from raghub_core.domain.providers.errors import ProviderTimeoutError

    for error in (CoreError("TEST", "test", details={"reason": "test"}), ProviderTimeoutError()):
        assert not hasattr(error, "status_code")
    violations = []
    for directory, _ in LAYERS.values():
        for path in directory.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (
                    isinstance(node, ast.keyword)
                    and node.arg == "status_code"
                    or isinstance(node, ast.Attribute)
                    and node.attr == "status_code"
                ):
                    violations.append(str(path.relative_to(APP.parent)))
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize(
    "source",
    [
        "from fastapi import UploadFile",
        "import sqlalchemy.orm",
        "from app.core.config import get_settings",
        "from app.modules.search import service",
        "def hidden():\n    from celery import Task",
        "from . import adapter",
    ],
)
def test_dependency_check_catches_runtime_and_hidden_imports(source: str) -> None:
    assert forbidden_imports(source, layer="domain")


def test_core_imports_with_app_and_infrastructure_blocked() -> None:
    script = """
import importlib
import importlib.abc
import pkgutil
import sys

class BlockInfrastructure(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        forbidden = {'fastapi', 'celery', 'redis', 'minio', 'elasticsearch',
                     'sqlalchemy', 'httpx', 'pymupdf', 'pydantic_settings'}
        if fullname.split('.')[0] in forbidden:
            raise AssertionError(f'Infrastructure import: {fullname}')
        if fullname == 'app' or fullname.startswith('app.'):
            raise AssertionError(f'Runtime import: {fullname}')

sys.meta_path.insert(0, BlockInfrastructure())
for package_name in ('raghub_core',):
    package = importlib.import_module(package_name)
    for module in pkgutil.walk_packages(package.__path__, package_name + '.'):
        importlib.import_module(module.name)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=APP.parent,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
