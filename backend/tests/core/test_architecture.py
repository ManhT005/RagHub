import ast
import subprocess
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
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
            if name == "app" or name.startswith("app."):
                allowed = ["app.core_domain"]
                if layer != "core_domain":
                    allowed.append("app.ports")
                if layer == "application":
                    allowed.append("app.application")
                if not any(name == value or name.startswith(value + ".") for value in allowed):
                    violations.append(name)
    return violations


def test_engine_dependency_direction() -> None:
    violations = []
    for layer in ("core_domain", "ports", "application"):
        assert (APP / layer).is_dir(), f"Missing engine layer: {layer}"
        for file in (APP / layer).rglob("*.py"):
            for name in forbidden_imports(file.read_text(encoding="utf-8"), layer=layer):
                violations.append(f"{file.relative_to(APP)}: {name}")
    assert not violations, "\n".join(violations)


def test_engine_errors_have_no_http_status_semantics() -> None:
    from app.core_domain.errors import CoreError
    from app.core_domain.providers.errors import ProviderTimeoutError

    for error in (CoreError("TEST", "test", details={"reason": "test"}), ProviderTimeoutError()):
        assert not hasattr(error, "status_code")
    violations = []
    for layer in ("core_domain", "application", "ports"):
        for path in (APP / layer).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (
                    isinstance(node, ast.keyword)
                    and node.arg == "status_code"
                    or isinstance(node, ast.Attribute)
                    and node.attr == "status_code"
                ):
                    violations.append(str(path.relative_to(APP)))
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
    assert forbidden_imports(source, layer="core_domain")


def test_core_imports_with_infrastructure_blocked() -> None:
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
        if fullname.startswith(('app.core.', 'app.infrastructure', 'app.modules', 'app.workers',
                                'app.composition', 'app.delivery')):
            raise AssertionError(f'Runtime import: {fullname}')

sys.meta_path.insert(0, BlockInfrastructure())
for package_name in ('app.core_domain', 'app.ports', 'app.application'):
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
