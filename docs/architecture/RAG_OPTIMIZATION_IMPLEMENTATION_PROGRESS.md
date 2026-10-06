# RAG optimization implementation progress

Source: [implementation plan](../../.backups/RAGHUB_RAG_OPTIMIZATION_IMPLEMENTATION_PLAN.md).
Branch: `feature/selfhost-rag-pipeline-upgrade`. Date: 2026-10-06.

## Scope and completion

This iteration completes the operational optimization scope requested after core
stabilization. The user clarified that local model/hardware results should remain
informational rather than rigid acceptance gates. Queue/capacity invariants,
recoverable ingestion, safe storage/publication, prompt bounds and diagnostics
were implemented and tested. No production quality or hardware speed improvement
is claimed without a deployment benchmark.

Reviewed 200?300-question data and deployment-specific model tuning remain
optional follow-up evaluation. The existing V2 draft remains 210 variants in
30 families with zero reviewed labels; it was not promoted or expanded as proof
of quality. The original backup plan is preserved. See the
[operations runbook](../runbook-rag-operations.md) for configuration and commands.

## Separate implementation commits

| Commit | Result |
|---|---|
| `30ca934` | Normalize semantic source blocks while retaining raw citation offsets; preserve code indentation and spreadsheet row metadata |
| `6391646` | Version normalized/context embedding pipelines, structural chunk links and durable metadata; validate vectors before replacement/publication |
| `2340bf1` | Match confidence artifacts to ready fused features; route adaptive reranking and select diverse evidence within the token budget |
| `888e2a5` | Reserve rendered evidence before conversation history; retain intact history pairs only within the remaining budget |
| `eec226f` | Run actual retrieval ablation cells and collect compatible calibration metadata; audit dataset family/split/format coverage |
| `bf82e9c` | Prioritize uploads, reserve admission capacity, interleave workspaces, hold local inference slots through cancellation and add hardware presets/cache counters |
| `db2a95b` | Keep evaluation gates optional; report honest TTFT, errors, support metrics and missing quality evidence |
| `ec787b4` | Resume storage/checkpoint failures, reuse already persisted vectors and reset failed work on explicit retry without losing completed batches |
| `00af02b` | Capture model-free operational diagnostics, emit optional JSON telemetry, bound chunk allocation and configure worker concurrency |
| Documentation commit | Record this scope, validation and operational rollout in this document and the runbook |

All commits are local; no push or deployment was requested or performed.

## Operational behavior

Core retains generic normalization, scheduling, confidence/evidence and prompt
policies; host composition owns model/hardware configuration and infrastructure.
Existing quota, index-version readiness and tenant isolation remain enforced.

Uploads precede background reindex work, with retry/recovery between them.
Workspace admission reserves upload capacity where the configured pending limit
allows it. Claim locks prevent duplicate ownership. Cloud quota retains query
reservation; local inference capacity is released only when native work ends.

Durable receipts retain batch progress through transient object-store failures.
A lost response after a successful vector write does not cause another provider
call on resume. Explicit retry recovers FAILED work targeting the active index.
Vector shape/key/count validation protects publication, and retrieval excludes
uncommitted evidence. Raw token and chunk caps bound document processing early.

Pipeline changes are opt-in and fingerprinted. Existing indices default to
`legacy`; `normalized-v1`/`context-v1` require a new version and reindex. Raw text
remains available for citations while normalized/enriched text serves search
and embeddings. Experimental evidence/adaptive flags default off in the custom
profile; CPU/GPU presets opt into selected capacity/routing defaults. A preset
does not enable OCR, install models or establish aggregate VRAM guarantees.

Operations snapshots need no AI calls. JSON telemetry is optional, excludes
content and can summarize saved stage timing/cache counters. Retrieval ablation
and model-answer evaluation are separate diagnostic tools and may call providers.
Missing labels produce unavailable quality metrics rather than invented scores;
threshold enforcement and reviewed-data checks require explicit opt-in.

## Verification

| Check | Result |
|---|---|
| Complete Core suite | 166 passed |
| Backend suite excluding integration marker | 567 passed; 56 deselected; six dependency deprecation warnings |
| Selected real infrastructure suites | 20 passed: durable work items, migration reconciliation, Redis quota and ingestion concurrency |
| Ruff across backend/Core source, scripts and tests | Passed |
| Compose configuration with GPU and OCR profiles | Passed; regular GPU concurrency two, OCR concurrency one |
| OpenAPI and Postman regeneration | No contract diff; 64 paths/86 operations and 85 collection items |

Infrastructure tests used a disposable Docker project with PostgreSQL, Redis,
Elasticsearch and MinIO. They covered database upgrades, exclusive claims,
priority/admission behavior, legacy Redis queue buckets, persisted vector reuse
and explicit retry preserving batch progress. The
[operations smoke artifact](../../artifacts/optimization-operations-smoke.json)
records an empty-stack snapshot with zero queued work and no infrastructure
issues; it is not a loaded performance or model-quality result.

No paid model calls, model downloads, live production edits or deployment were
needed for this verification. Local quality/latency results are not blockers for
the completed operational scope. Origin/develop is incorporated without another
history rewrite; unrelated remote branches are not merged.
