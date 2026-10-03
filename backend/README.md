# RagHub backend and engine

The `raghub-backend` distribution contains two Python packages:

- `raghub_core`: domain, application workflows, ports and the supported
  `raghub_core.api` facade. It does not import the runtime host.
- `app`: self-host/public-chat/worker composition, delivery, adapters,
  authentication and the control plane.

This phase keeps one distribution and one version. It does not publish a separate
`raghub-core` wheel. Installing normal backend dependencies supports the complete
host; the engine contract suite uses the minimal test lock instead.

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
