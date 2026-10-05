# Standalone Core and self-host backend verification

Verified locally on **2026-10-05**, on `feature/selfhost-ui-v1`. This is a local
refactor on the existing branch; it has not been committed or pushed. The previous
combined-wheel reports remain historical. See [ADR-001](adr/ADR-001-core-package-boundary.md)
for the updated package decision.

## Resulting boundary

```text
raghub-core/
  pyproject.toml          raghub-core distribution; tiktoken runtime dependency
  src/raghub_core/        domain, application, ports, api.py and tokenizer asset
  tests/                 engine contracts, architecture gates and fake ports
  requirements-test.lock minimal core test dependencies
backend/
  pyproject.toml          raghub-backend distribution; versioned core dependency
  app/                   self-host delivery, composition, control plane and adapters
  tests/                 host architecture, unit/HTTP and live integration tests
```

All **60 engine source/asset files** are byte-identical to their pre-move copies,
including all **59 Python modules** and the bundled tokenizer cache. The import
namespace, supported facade, commands, results and workflows are unchanged.
`backend/app` and Alembic migration sources are unchanged. There is no compatibility
copy or symlink at `backend/raghub_core`; backend consumes the installed core.

Backend declares `raghub-core==0.1.0` and maps the editable sibling source for uv.
The standalone project has its own metadata, test configuration and uv lock.
Backend's existing locked third-party versions are preserved. Core's source
distribution includes the complete tests, fake ports and minimal test lock.

## Checks

| Check | Local result |
| --- | --- |
| Core suite in the development environment | **112 passed** |
| Backend suite after separation | **274 passed, 15 skipped**; live integrations require an external stack |
| Regression total | **386 passed**, matching the pre-refactor total; tests moved between projects |
| Core suite against the installed wheel in a fresh minimal venv | **112 passed**, with no backend/runtime dependencies installed |
| Installed-wheel import isolation | All **59 modules** imported from the installed core wheel with `app` and runtime libraries blocked |
| Cold tokenizer and fake-port lifecycle | Offline cache restoration and roundtrip passed; upload-to-chat lifecycle **1 passed** |
| Wheel boundaries | Core contains engine and tokenizer asset, no `app`; backend contains `app`, no engine, and declares the matching core version |
| Source distributions and wheels | Both projects built successfully |
| uv lock consistency | Both project locks passed `uv lock --check` |
| Ruff | Backend, core and package/Compose check scripts passed |
| Compose | Development runtime/local-AI, GHCR variants, self-host CPU/GPU, source build and required-setting checks passed |
| Workflow lint | actionlint **1.7.7 passed** |
| Docker builds | `runtime` and CPU `local-ai` targets built with repository-root context and distinct verification tags |
| Production container smoke | Core loaded from site-packages; all modules, offline tokenizer, API, provider cipher and Celery worker imported successfully |
| Development mount smoke | The same checks passed with sibling core source mounted at `/app/raghub_core` |
| Local-AI container smoke | Production checks plus Sentence Transformers and CPU-only PyTorch imports passed |

The reindex HTTP regression still asserts **409 `REINDEX_IN_PROGRESS`** and is
included in the passing backend suite. CI-only provider key configuration from the
preceding CI fix remains in both relevant jobs.

## Reproduce

Use Python 3.12 and an activated virtual environment. From the repository root:

```sh
python -m pip install -r backend/requirements.lock
python -m pip install --no-deps -e ./raghub-core -e ./backend
python -m ruff check backend raghub-core scripts/check-core-package.py scripts/check-compose.py
```

Run `python -m pytest -p no:cacheprovider` from `raghub-core`. Run the same command
from `backend`, setting `PROVIDER_MASTER_KEY=raghub-ci-provider-key-not-for-production`
for tests. PowerShell uses `$env:PROVIDER_MASTER_KEY = 'raghub-ci-provider-key-not-for-production'`.
Build/verify both packages with the commands in the [core README](../../raghub-core/README.md#build-and-verify-packages).
Validate Compose with `python scripts/check-compose.py`.

```sh
docker build -f backend/Dockerfile --target runtime -t raghub/backend-core-split:local .
docker build -f backend/Dockerfile --target local-ai -t raghub/backend-core-split:local-ai .
docker run --rm -v "$PWD:/repo:ro" -w /repo rhysd/actionlint:1.7.7 -shellcheck= -pyflakes=
```

## Limits

Live PostgreSQL/Redis/object-store integration and a complete running self-host
installation were not rerun for this layout refactor. Container smoke used
`--network none`, test-only credentials and disposable containers; it verifies
packaging and imports rather than live provider inference or ingestion. No existing
installation, persistent volume, schema or frontend code was changed. GPU execution
and external paid providers are outside these checks. GitHub Actions has not run
against this local refactor, and neither Python package has been published to a
registry.
