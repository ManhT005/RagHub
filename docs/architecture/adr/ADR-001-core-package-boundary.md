# ADR-001: Standalone Core package and self-host host

Status: Accepted, updated 2026-10-05.

## Context

The engine already has an enforced dependency boundary and a stable `raghub_core`
namespace, but was stored in `backend/raghub_core` and distributed inside the
`raghub-backend` wheel. That layout obscured the self-host backend's role as a
consumer of the reusable engine. Standalone packaging was previously deferred.

## Decision

Move the engine unchanged into `raghub-core/src/raghub_core`, alongside `backend`.
Build a standalone `raghub-core` package with only `tiktoken` as a runtime dependency
and bundle its existing tokenizer asset. Core tests and their minimal dependency
lock belong to that project. The import namespace and public API remain unchanged.

The `raghub-backend` package contains only `app` and depends on `raghub-core==0.1.0`.
It implements self-host composition, HTTP delivery, control plane, auth and concrete
infrastructure adapters. The dependency direction remains backend -> core.
`app/core` is backend runtime support, not the reusable engine.

Local development installs both projects, with editable core source. Docker uses
the repository root as its context and installs core from its sibling project.
Development mounts/watches both source trees; production imports the installed core.
CI verifies engine contracts, the standalone installed wheel, backend contracts,
integration, migrations and image builds.

## Consequences

The core can be installed and tested independently of the self-host backend.
Backend consumers must install core explicitly rather than rely on a nested folder
or an ad hoc `PYTHONPATH`. Both packages initially retain version `0.1.0`; future
core compatibility changes require an explicit backend dependency update.

This decision changes repository layout and packaging, not workflows, transactions,
HTTP contracts, schema, authorization or deployment policy. It does not publish a
package to PyPI, add a new host or claim cloud/SaaS support. Existing operational
verification reports describe the layout at the time of their runs; the sibling
package refactor has its own verification report.
