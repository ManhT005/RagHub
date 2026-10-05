# Contributing

## Branches

Create work from an up-to-date `develop` branch. Use one of these prefixes:

- `feature/<short-name>` for product work.
- `fix/<short-name>` for defect fixes.
- `chore/<short-name>` for maintenance and tooling.
- `docs/<short-name>` for documentation-only changes.

Merge reviewed work into `develop`. Reserve `main` for release-ready commits.

## Commits

Use Conventional Commits in the form `type(scope): summary`, for example:

```text
feat(ingestion): index PDF pages in Elasticsearch
fix(api): preserve request ID in error responses
chore(compose): pin infrastructure images
```

Keep a commit focused, do not commit secrets, and include tests for changed
behavior where practical.

## Python projects

Use Python 3.12 and an activated virtual environment. `raghub-core` is the reusable
engine; `backend` is its self-host host and adapters. From the repository root:

```sh
python -m pip install -r backend/requirements.lock
python -m pip install --no-deps -e ./raghub-core -e ./backend
python -m ruff check backend raghub-core
```

Run core tests from `raghub-core` with `python -m pytest -p no:cacheprovider`.
Run backend tests from `backend` with the same command, setting
`PROVIDER_MASTER_KEY=raghub-ci-provider-key-not-for-production` for unit tests.
PowerShell uses `$env:PROVIDER_MASTER_KEY = 'raghub-ci-provider-key-not-for-production'`.
Integration tests require a disposable Docker stack and `RAGHUB_TEST_*` settings.
Core composition uses `raghub_core.api`; host adapters implement core ports.
Keep host/runtime imports out of the core and run both suites after boundary changes.
