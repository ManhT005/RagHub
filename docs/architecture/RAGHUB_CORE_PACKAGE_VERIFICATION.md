# Physical Core package verification

This is the historical combined-wheel verification from 2026-10-04. The current
layout uses standalone `raghub-core` alongside `backend`; see the
[sibling package verification](RAGHUB_CORE_SIBLING_VERIFICATION.md) and
[ADR-001](adr/ADR-001-core-package-boundary.md) for the superseding package decision.

Verified locally on **2026-10-04**, branch `refactor/core-package`. The work starts
at `d82e5ba` and merges `origin/develop` at `854dcaf` before moving engine code.
The merge preserves Console navigation and incorporates the new provider-select,
configuration/publication and standalone embed flows. The consolidation plan is
ignored and is not included in any implementation commit.

## Package and contract evidence

The canonical implementation is now `backend/raghub_core/{domain,ports,application}`.
`raghub_core.api` selectively exports supported use cases, commands, result types
and typed RAG events. `app` contains host composition, delivery, adapters and the
control plane. The retired `app/core_domain`, `app/ports` and `app/application`
directories are absent, and production import checks reject those namespaces.

The [public API](RAGHUB_CORE_PUBLIC_API.md) was frozen in a separate commit before
the move. Domain, ports, application, host rewiring, architecture/API gates,
packaging and compatibility removal each have separate commits. No new document
formats, reranking, OCR, role redesign or deployment-mode policy was introduced.

A local AST comparison checked all **57 migrated engine Python modules** against
the frozen baseline, after normalizing import paths and excluding top-level import
ordering. All bodies match. The bundled tokenizer asset is byte-identical.

## Automated checks

| Check | Result |
| --- | --- |
| Sync regression before the move | 291 backend tests, 15 live integration tests, 85 frontend tests and four widget tests passed |
| Minimal-dependency core suite after consolidation | **86 passed** with `requirements-core-test.lock` |
| Backend unit regression after compatibility removal | **319 passed**, 15 integration tests deselected |
| Final full backend/live suite | **334 passed**, including 15 live integration tests |
| Frontend | **85 passed** across 15 files; production and runtime-image builds passed |
| Widget | **4 passed**; TypeScript compilation passed |
| Schema | Alembic head remains `20261003_0012`; final runtime `alembic check` reports no pending model changes |
| Compose | Runtime/local-AI development, registry deployment, CPU/GPU self-host and mandatory-secret checks passed |
| Workflows | actionlint 1.7.7 passed with `core-package-isolation` |
| Docker | Runtime and CPU local-AI images built; image inspection confirmed canonical engine and no retired namespaces |

Architecture tests reject every `app` import in each engine layer, upward domain/
port dependencies, unapproved third-party libraries and hidden imports. A fresh
subprocess blocks the host/runtime namespace and imports every engine module.
The complete fake-port upload-to-chat test now consumes the supported API facade.

The development API and worker bind/watch both `app` and `raghub_core`. Production
images copy both packages. Package metadata is copied with application code so
metadata-only edits do not invalidate shared runtime/CPU AI dependency layers.

## Installed wheel

`python -m build` produced the backend source distribution and
`raghub_backend-0.1.0-py3-none-any.whl`. It keeps the existing distribution name,
version and runtime dependencies; a separate `raghub-core` wheel is not created.
The wheel contains `app`, `raghub_core` and the canonical compressed tokenizer
asset, and contains none of the retired compatibility namespaces.

`scripts/check-core-package.py` verified the final wheel by creating a fresh venv,
installing only the minimal test lock and the wheel with `--no-deps`, then running
Python with `-I` from outside the source checkout. **All 59 engine modules** loaded
from that venv's installed wheel with `app` and runtime libraries blocked. Tokenizer
data was restored into an initially empty cache and encoding/decoding passed.
The complete fake-port lifecycle passed against installed code. No Docker, database,
Redis or AI model is needed for that lifecycle.

CI retains all existing jobs and adds `core-package-isolation`, depending on
`core-contracts`. Docker image verification/publication also requires that job.

## Self-host CPU lifecycle

The final application/restart verification **passed**. The disposable target is
`raghub-package-selfhost`, with fresh database, object, index and Redis volumes.
Only checksum-verified Ollama/Hugging Face model caches are reused from the previous
local smoke backup. Production test seeds and manual database inserts are not used.

The smoke used actual Sentence Transformer `all-MiniLM-L6-v2` (384 dimensions)
and Ollama `gemma3:1b` on CPU, without an external API key. It verified CLI owner
bootstrap and idempotency/password preservation, login, workspace/provider creation
and connectivity, binding, API upload, worker ingestion to READY, retrieval,
Playground streaming, publication, embed configuration, allowed/denied origins,
preflight, public SSE, trusted citations, served widget and Console shell.

After restarting all persistent runtime services, it repeated owner login,
retrieval and both chat entry points and proved that configuration, documents,
index, model and embed key survived. This exercises the shared physical package
through self-host, worker and public-chat composition roots. The final Console
build also aligns global dark-theme selectors with the renamed Console shell.
After that final frontend image was recreated, the gateway served the new Console
stylesheet with no retired shell selectors, while API readiness remained healthy.

## Release limits

Local verification does not replace green full PR CI targeting `develop`. No remote
release was published, and no push or merge into `develop` is part of this work.
GPU configuration is structurally checked; hardware GPU execution and paid external
providers are outside this consolidation. UI checks are component/Router tests and
builds, rather than browser automation.

The UI redesign increases the production initial bundle to **1.97 MB**; it retains
the existing 1.25 MB budget warning. Alembic retains the existing cyclic-foreign-key
sorting warning for workspaces/embedding-index versions while schema comparison
passes. Backup/restore/upgrade implementation remains unchanged; its earlier live
evidence is in [self-host verification](../operations/SELF_HOST_VERIFICATION.md).
