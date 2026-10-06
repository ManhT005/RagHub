# RAG core stabilization execution

Source: `.backups/RAGHUB_RAG_CORE_STABILIZATION_OPTIMIZATION_PLAN.md`.

## Branch baseline

The owner confirmed that develop was already rebased into this branch. Preserve
that baseline; do not merge or rebase it again. A preliminary merge was aborted
without retaining changes. Baseline core suite: 150 passed.

## Phase 1: core boundaries

Admissions policy and its regression cases now live in the host. Core accepts a
clarification policy port and defaults to a generic policy. New chatbot defaults
are generic; migration 0025 preserves existing explicit profile selections.
Provider quota presets and model catalogs now live in the host. An explicit host
context-window override supports unknown local models.

Validation: core 123 passed; host boundary, admissions, clarification evaluation,
quota scheduling and prompt-budget suites 76 passed. The lower core count reflects
moving 29 domain-specific cases into the host and adding two generic cases.

## Verification still required against running infrastructure

Clean/current DB upgrades, restart/concurrent worker integration, production model
download/checksum, recalibration and hardware benchmarks require real services
and model artifacts. Unit or fixture evaluation must not be reported as evidence
of those production acceptance criteria.

## Phases 2, 10, 11: publish and retrieval correctness

The pre-index hook keeps INDEXING. Elasticsearch writes non-retrievable chunks,
validates their count, then publishes. The existing rebuild creates a separate
inactive index and only switches the active version after validation.
Runtime RRF receives configured k. Relevance runs before reranking and fails open
when the active embedding fingerprint differs or is missing. Calibration now
standardizes features and requires a fingerprint; artifact loading rejects
nonfinite parameters, unknown features and invalid normalization arrays.

Validation: host index/retry/readiness/reindex/hybrid/relevance suites 58 passed.

## Phase 14: rendered prompt budgeting

Budget selection counts final guardrail, citation metadata, context and history
using the same renderer used for generation. Host context limits are explicit;
there is no preliminary context truncation in model-aware chat. History also
respects remaining space. An empty budgeted context skips generation. Output
limits and a low factual-generation temperature reach ChatOptions.

Validation: core 127 passed; host prompt/citation/empty/public chat suites 26 passed.

## Phases 3?4: structural representation and chunking

ParsedBlock extends the compatibility ParsedSection contract. DOCX/HTML keep
heading paths; PDF tables are distinct blocks and OCR uses image/text signals.
Adjacent paragraphs merge within the same heading/page. Chunking prefers sentence
and paragraph boundaries, uses 60-token overlap, and preserves table rows while
repeating headers and row ranges. A single oversized row is kept intact rather
than silently split; target size is soft for such rows.

Validation: core 127 passed; parser/chunker suites 29 passed, including all-row
coverage, nested hidden HTML, DOCX heading merging and safety limit regressions.
