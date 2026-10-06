# RAG core stabilization execution

Source: `.backups/RAGHUB_RAG_CORE_STABILIZATION_OPTIMIZATION_PLAN.md`.

## Branch baseline

A refreshed fetch and reflog inspection found that the October 6 rebase operated
on local develop, not the RAG feature branch. Origin/develop had 17 missing commits.
A merge now reconciles those commits without rewriting the RAG commit history.
Workspace reranking, local model downloads, provider validation and widget updates
are preserved alongside the stabilization changes.

Develop keeps revisions 0021/0022. RAG pools/work items move to unique 0027/0028;
0023 depends on 0028. New head 0029 repairs missing upstream tables on previously
stamped RAG databases. Already applied pool/work-item schemas are detected rather
than recreated. Migration order follows Alembic ancestry, not numeric sorting.
Verified upgrade: empty DB, origin/develop head 0022, and pre-merge RAG head 0026.
All reach 0029 with both upstream and RAG structures present.

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

Migration upgrades and service integration were verified on an isolated Docker
project. Production model artifacts, recalibration and hardware benchmarks still
require deployment-specific evidence. Unit or fixture evaluation must not be reported as evidence
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

## Phases 3-4: structural representation and chunking

ParsedBlock extends the compatibility ParsedSection contract. DOCX/HTML keep
heading paths; PDF tables are distinct blocks and OCR uses image/text signals.
Adjacent paragraphs merge within the same heading/page. Chunking prefers sentence
and paragraph boundaries, uses 60-token overlap, and preserves table rows while
repeating headers and row ranges. A single oversized row is kept intact rather
than silently split; target size is soft for such rows.

Validation: core 127 passed; parser/chunker suites 29 passed, including all-row
coverage, nested hidden HTML, DOCX heading merging and safety limit regressions.

## Phases 5-8: canonical durable embeddings and cache

Host upload and reindex both inject ResumableEmbedding into the core builder.
The fallback engine also batches its requests. Work items persist fingerprint,
index and dimension; local providers use the same work-item/checkpoint mechanism
without a cloud quota. Index completion is required before COMPLETED. The batch
worker now commits checkpoints and publishes actual document vectors rather than
writing a receipt. Conditional SKIP LOCKED claims and workspace admission locks
serialize work; caps come from settings. Retry reuses completed artifacts,
including an artifact saved before a checkpoint commit. Optional tenant-scoped
embedding cache keys include fingerprint and content hash.

Validation: core 127 passed; embedding/claim/provider/ingestion/reindex suites 55
passed; restart/cache tests 4 passed; real PostgreSQL claim + MinIO/Elasticsearch
upload 2 passed; real Redis quota and ingestion concurrency 8 passed. Clean DB
upgrade through 0026 succeeded on a disposable Docker project with isolated ports.

## Phases 8-13: runtime policies

Queries reserve interactive quota before calling Gemini, sharing project/model
buckets with background batches. Local providers bypass cloud quota. Authentication
failures disable a pool credential and permit failover only inside the immutable
profile; 429 never hops keys. Snapshot fingerprint corruption fails before provider
resolution. Quota deferrals receive their own patient retry budget.

Optional neighbor expansion stays tenant/version scoped and readiness filtered.
Adaptive clarification receives pre-rerank confidence without resolving a chat
provider. Both remain disabled by default. Calibration features now match the
five-candidate collection window and invalidate older configuration hashes.

The local reranker revision is a full commit SHA. Runtime verifies a deployment
snapshot checksum before loading weights, never downloads models, bounds loading
and inference, and limits outstanding inference even after a timeout. A preparation
CLI supplies the deploy-time checksum. Approved artifacts and hardware performance
measurements still need deployment-specific verification.

## Phases 12, 17, 19: deployment and gates

OCR uses a dedicated profile/queue, concurrency one, and optional Docker targets
with English/Vietnamese Tesseract. When OCR is enabled, whole ingestion/reindex
jobs route to that worker: mixed documents keep one durable pipeline, at the cost
of throttling all ingestion in that deployment. Regular workers retain the legacy
celery queue and consume the new ingestion/reindex/embedding queues. OCR timing
and page counts contain no document content. Batch timing and cache counters are
also available. Nightly service tests now include real ES/MinIO uploads.

Reranker measurement uses configured DB/search services, explicit tenant IDs and
reviewed local snapshots. It does not mint tokens for a hardcoded user or download
unverified weights. Release gates accept optional MRR/nDCG/hit and latency limits;
missing explicitly required evidence fails the gate. Citation ID validity remains
separate from semantic support: reviewed claim-support labels are still needed.

Remaining acceptance: the golden corpus currently contains 30 questions. Phase 18
requires a curated 200-300 case corpus, support judgments, and deployment-specific
calibration/CPU-GPU benchmarks. Do not inflate fixture counts or promote lexical
compare-only reports to production quality evidence.
