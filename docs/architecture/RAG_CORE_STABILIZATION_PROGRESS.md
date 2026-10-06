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
