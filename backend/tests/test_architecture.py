import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
COMPOSITION = APP / "composition"


def composition_internal_imports(source: str) -> list[str]:
    violations = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [module, *(f"{module}.{alias.name}" for alias in node.names)]
        for name in names:
            if name == "raghub_core.application" or name.startswith("raghub_core.application."):
                violations.append(name)
    return violations


def test_composition_does_not_import_core_application_internals() -> None:
    assert COMPOSITION.is_dir()
    violations = []
    for file in COMPOSITION.rglob("*.py"):
        for name in composition_internal_imports(file.read_text(encoding="utf-8")):
            violations.append(f"{file.relative_to(APP.parent)}: {name}")
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize(
    "source",
    [
        "from raghub_core.application.rag.stream_chat import StreamRagChatUseCase",
        "import raghub_core.application",
        "import raghub_core.application.rag.stream_chat as runtime",
        "from raghub_core import application as internal",
        "def hidden():\n    from raghub_core.application import rag",
        "if TYPE_CHECKING:\n    from raghub_core.application import rag",
    ],
)
def test_composition_gate_rejects_internal_and_hidden_imports(source: str) -> None:
    assert composition_internal_imports(source)


@pytest.mark.parametrize(
    "source",
    [
        "from raghub_core.api import StreamRagChatUseCase",
        "from raghub_core import api",
        "from raghub_core.ports.vector_store import VectorStorePort",
        "from raghub_core.domain.ingestion.chunker import chunk_sections",
        "from raghub_core.domain.retrieval.models import RetrievalScope",
        "from app.infrastructure.object_storage.minio import MinioObjectStorage",
    ],
)
def test_composition_gate_allows_facade_and_adapter_wiring(source: str) -> None:
    assert not composition_internal_imports(source)


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


def test_production_hosts_use_canonical_core_imports() -> None:
    legacy = ("app.core_domain", "app.application", "app.ports")
    violations = []
    for file in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            for name in names:
                if any(name == root or name.startswith(root + ".") for root in legacy):
                    violations.append(f"{file.relative_to(APP)}: {name}")
    assert not violations, "\n".join(violations)


def test_retired_core_namespaces_are_absent() -> None:
    for directory in ("core_domain", "application", "ports"):
        assert not (APP / directory).exists(), f"Retired engine namespace remains: {directory}"

