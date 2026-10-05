"""Validate standalone engine isolation and the self-host wheel dependency boundary."""

import argparse
import os
import shutil
import subprocess
import tempfile
import venv
import zipfile
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SMOKE = """
import importlib
import importlib.abc
import pkgutil
import sys
import tempfile
from pathlib import Path

class BlockHost(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        forbidden = {'app', 'fastapi', 'starlette', 'sqlalchemy', 'celery',
                     'redis', 'minio', 'elasticsearch', 'httpx', 'pydantic_settings',
                     'pymupdf', 'pydantic'}
        if fullname.split('.')[0] in forbidden:
            raise AssertionError(f'Host/runtime dependency: {fullname}')

sys.meta_path.insert(0, BlockHost())
cache = Path(tempfile.gettempdir()) / 'raghub-token-cache'
assert not cache.exists(), 'Tokenizer verification requires an empty cache'
package = importlib.import_module('raghub_core')
modules = [package]
for info in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
    modules.append(importlib.import_module(info.name))
for module in modules:
    assert Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), (
        f'Imported source instead of the installed wheel: {module.__file__}'
    )
assert not any(name == 'app' or name.startswith('app.') for name in sys.modules)
tokenizer = importlib.import_module('raghub_core.domain.ingestion.tokenizer')
assert cache.is_dir() and any(cache.iterdir()), 'Bundled tokenizer cache was not restored'
text = 'RagHub engine: ORCHID-729'
assert tokenizer.ENCODING.decode(tokenizer.ENCODING.encode(text)) == text
print(f'PASS: {len(modules)} wheel modules imported with app/runtime blocked; cold tokenizer works',
      flush=True)

# Only the copied fake-port tests are added. The repository/source tree is never on sys.path.
directory = Path(__file__).resolve().parent
sys.path.insert(0, str(directory))
import pytest
raise SystemExit(pytest.main([
    '-p', 'no:cacheprovider', str(directory / 'tests/core/test_engine_flow.py'),
    '--override-ini', 'asyncio_mode=auto',
    '--override-ini', 'asyncio_default_fixture_loop_scope=function', '-q',
]))
"""


def run(command, directory, *, environment=None, label):
    print(label, flush=True)
    result = subprocess.run(
        command,
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        print(result.stdout[-5000:], result.stderr[-5000:], flush=True)
        raise RuntimeError(f"{label} failed (exit {result.returncode})")
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--backend-wheel", type=Path, required=True)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        required = {
            "raghub_core/__init__.py",
            "raghub_core/api.py",
            "raghub_core/application/rag/stream_chat.py",
            "raghub_core/ports/object_storage.py",
        }
        if not required.issubset(names):
            raise ValueError("Core wheel is missing canonical engine modules")
        if any(
            name.startswith("app/")
            for name in names
        ):
            raise ValueError(
                "Core wheel must not contain the self-host package"
            )
        assets = [
            name
            for name in names
            if name.startswith("raghub_core/domain/ingestion/token_cache/")
            and name.endswith(".gz")
        ]
        if len(assets) != 1:
            raise ValueError("Wheel must include its bundled tokenizer asset")
        metadata_path = next(name for name in names if name.endswith(".dist-info/METADATA"))
        core_metadata = Parser().parsestr(archive.read(metadata_path).decode("utf-8"))
        runtime_requirements = [
            requirement for requirement in core_metadata.get_all("Requires-Dist", [])
            if "extra ==" not in requirement
        ]
        if core_metadata["Name"] != "raghub-core" or runtime_requirements != ["tiktoken==0.9.0"]:
            raise ValueError("Core runtime dependencies must remain minimal")
    print(
        "PASS: standalone core wheel contains engine and tokenizer asset without app",
        flush=True,
    )
    backend_wheel = args.backend_wheel.resolve(strict=True)
    with zipfile.ZipFile(backend_wheel) as archive:
        names = set(archive.namelist())
        if "app/main.py" not in names or any(
            name.startswith(("raghub_core/", "app/core_domain/", "app/application/", "app/ports/"))
            for name in names
        ):
            raise ValueError("Self-host wheel must contain app without bundled engine or aliases")
        metadata_path = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = Parser().parsestr(archive.read(metadata_path).decode("utf-8"))
        requirements = metadata.get_all("Requires-Dist", [])
        if not any(requirement.replace(" ", "") == f"raghub-core=={core_metadata['Version']}"
                   for requirement in requirements):
            raise ValueError("Self-host wheel must declare its versioned core dependency")
    print("PASS: self-host wheel depends on standalone core; core only needs tiktoken", flush=True)
    with tempfile.TemporaryDirectory(prefix="raghub-core-wheel-") as temporary:
        directory = Path(temporary)
        environment = directory / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "-r",
                str(ROOT / "raghub-core/requirements-test.lock"),
            ],
            directory,
            label="Install minimal core dependencies into a fresh venv",
        )
        run(
            [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
            directory,
            label="Install standalone core wheel",
        )
        output = run(
            [
                str(python), "-I", "-m", "pytest", "-p", "no:cacheprovider",
                str(ROOT / "raghub-core/tests"),
            ],
            directory,
            label="Run all core contracts against the installed wheel with minimal dependencies",
        )
        print(output, end="", flush=True)
        shutil.copytree(
            ROOT / "raghub-core/tests",
            directory / "tests/core",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        (directory / "tests/__init__.py").write_text("", encoding="utf-8")
        smoke = directory / "installed_smoke.py"
        smoke.write_text(SMOKE, encoding="utf-8")
        cache_directory = directory / "cold-cache"
        cache_directory.mkdir()
        output = run(
            [str(python), "-I", str(smoke)],
            directory,
            environment={
                **os.environ,
                "TMPDIR": str(cache_directory),
                "TEMP": str(cache_directory),
                "TMP": str(cache_directory),
            },
            label="Block app imports and run installed-wheel tokenizer plus fake-port lifecycle",
        )
        print(output, end="", flush=True)
    print(
        "PASS: minimal core suite, installed-wheel isolation and fake-port lifecycle", flush=True
    )


if __name__ == "__main__":
    main()
