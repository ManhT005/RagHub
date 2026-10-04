# RagHub backend and engine

The `raghub-backend` distribution contains two Python packages:

- `raghub_core`: domain, application workflows, ports and the supported
  `raghub_core.api` facade. Host composition must import public use cases through
  this facade. The engine does not own HTTP delivery, persistence implementation,
  Redis admission, deployment mode or product administration.
- `app`: self-host/public-chat/worker composition, delivery, adapters,
  authentication, Redis, provider clients, MinIO, Elasticsearch, Celery and the
  control plane. Infrastructure implements `raghub_core.ports` directly and may
  use their domain contracts; the facade does not replace ports.

`raghub_core` is physically and dependency isolated, but is currently distributed
inside the `raghub-backend` Python distribution. A separately versioned
`raghub-core` distribution is intentionally **Deferred**; namespace isolation is
not an independent release package. See [ADR-001](../docs/architecture/adr/ADR-001-core-package-boundary.md)
for the decision and future extraction triggers. Installing normal backend
dependencies supports the complete host; the engine contract suite uses the
minimal test lock instead.

From this directory:

```sh
python -m pip install -r requirements-core-test.lock
python -m pytest -p no:cacheprovider tests/core
python -m pip install build==1.2.2.post1
python -m build
python ../scripts/check-core-package.py --wheel dist/raghub_backend-0.1.0-py3-none-any.whl
```

The wheel check creates a fresh venv, installs minimal dependencies plus the wheel
without host dependencies, blocks `app` imports, imports every engine module,
restores the bundled tokenizer into an empty cache and runs the complete fake-port
upload-to-chat lifecycle. The repository source tree is excluded from that smoke.

See the repository's `docs/architecture/RAGHUB_CORE_PUBLIC_API.md` for the frozen
contracts and `docs/operations/SELF_HOST.md` for the complete host installation.
