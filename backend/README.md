# RagHub self-host backend

`raghub-backend` packages `app`: the self-host host and infrastructure adapters for
the standalone [RagHub Core](../raghub-core/README.md) engine. Core source and
contract tests live alongside this directory in `../raghub-core`.

`app` owns composition, HTTP/public-chat delivery, authentication/RBAC, the control
plane, provider credentials and clients, persistence, Redis admission, MinIO,
Elasticsearch and Celery workers. Composition imports supported use cases through
`raghub_core.api`; adapters implement `raghub_core.ports` and use domain contracts.
The engine never imports the backend.

## Develop and test

Use Python 3.12. From this directory, in an activated virtual environment:

```sh
python -m pip install -r requirements.lock
python -m pip install --no-deps -e ../raghub-core -e .
PROVIDER_MASTER_KEY=raghub-ci-provider-key-not-for-production python -m pytest -p no:cacheprovider
python -m ruff check . ../raghub-core
```

In PowerShell, set `$env:PROVIDER_MASTER_KEY` before running pytest. The example key
is for tests only. Live integration tests require the existing Docker stack and
`RAGHUB_TEST_*` settings; without them those tests skip. Run the independent engine
suite separately from `../raghub-core`. Architecture tests here enforce host
composition and delivery boundaries.

`uv sync --extra dev` installs the editable sibling core through the local source
mapping in `pyproject.toml`. The backend wheel pins `raghub-core==0.1.0`; source
installation therefore installs both local projects as shown above.

## Docker

Build from the repository root so the build can read both projects:

```sh
docker build -f backend/Dockerfile --target runtime -t raghub/backend:local .
```

The Dockerfile installs core as a package and copies the self-host application.
API, worker and migration share the resulting image. Development Compose mounts
both source trees and watches them for reload; production uses the installed core.
The `local-ai` target adds CPU model dependencies to the same host/core layout.
The Dockerfile-specific ignore file limits the root context to required sources.

See [core package verification](../raghub-core/README.md#build-and-verify-packages),
the [public API](../docs/architecture/RAGHUB_CORE_PUBLIC_API.md) and
[self-host installation](../docs/operations/SELF_HOST.md).
