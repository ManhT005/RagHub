# RagHub Core

`raghub-core` is the reusable knowledge and RAG engine. It is a standalone Python
package alongside the self-host backend; its import namespace remains `raghub_core`.

- `domain`: policies, algorithms, commands, results and typed events.
- `application`: document, ingestion, reindex, retrieval, RAG and chatbot workflows.
- `ports`: interfaces implemented by a host's infrastructure adapters.
- `api.py`: supported public use cases and contracts consumed by host composition.

The engine never imports `app`, FastAPI, SQLAlchemy, Celery, Redis, MinIO,
Elasticsearch, HTTP provider clients or host settings. Its only runtime dependency
is `tiktoken`; the tokenizer data is bundled in the wheel for offline startup.
HTTP delivery, authentication, the control plane, credentials, database and queue
implementations remain in `../backend/app`.

## Develop and test

Use Python 3.12. From this directory, in an activated virtual environment:

```sh
python -m pip install -r requirements-test.lock
python -m pip install --no-deps -e .
python -m pytest -p no:cacheprovider
```

The suite runs without a backend installation, database, Docker or AI credentials.
It preserves the public API, rejects host/runtime imports and exercises the full
upload-to-chat lifecycle with fake ports. Backend-specific architecture checks
live in `../backend/tests/test_architecture.py`.

## Build and verify packages

From the repository root:

```sh
python -m pip install build==1.2.2.post1
python -m build raghub-core
python -m build backend
python scripts/check-core-package.py \
  --wheel raghub-core/dist/raghub_core-0.1.0-py3-none-any.whl \
  --backend-wheel backend/dist/raghub_backend-0.1.0-py3-none-any.whl
```

The check imports every engine module from an installed core wheel in a fresh
minimal environment with the host blocked, runs all core contracts, restores a cold
tokenizer cache and runs the fake-port lifecycle. It also verifies that the backend wheel declares a
core dependency and does not bundle engine code. Both packages currently use
version `0.1.0`; backend pins that compatible core version. Neither package is
published to a registry by this refactor.

See the [public API](../docs/architecture/RAGHUB_CORE_PUBLIC_API.md),
[boundaries](../docs/architecture/RAGHUB_CORE_BOUNDARIES.md) and
[package decision](../docs/architecture/adr/ADR-001-core-package-boundary.md).
