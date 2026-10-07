# Embedding execution and progress

Upload ingestion parses/chunks once, saves an immutable chunk manifest and batch
layout, then dispatches `embedding.process_work_item_batch`. The parent returns
`EMBEDDING_QUEUED`. Each delivery processes a bounded window, commits successful
checkpoints independently, and schedules the next window immediately.
Quota/provider retries stay on the embedding queue and reuse completed artifacts.
Local execution stays sequential. Reindex uses the same bounded executor inline
so its existing index activation workflow remains intact.

Upgrade with `python -m alembic upgrade head` before restarting API and workers.
Revision `0032` adds workspace preferences and work-item execution snapshots.
Legacy items without a snapshot keep the previous batch settings (24 chunks /
10,000 tokens unless explicitly configured); preserve those settings until their
backlog drains. New items snapshot the selected policy. Speed changes do not
change vector fingerprints or require reindexing.

## Policies and limits

| Profile | Inflight requests | Chunks/batch | Target tokens/batch |
|---|---:|---:|---:|
| conservative | 1 | 16 | 8,000 |
| balanced (default) | 2 | 32 | 20,000 |
| fast | 4 | 48 | 35,000 |
| custom | Configured | Configured | Configured |

`RAG_EMBEDDING_SPEED_PROFILE` selects the host default.
`RAG_EMBEDDING_MAX_INFLIGHT_HARD_CAP` (4),
`RAG_EMBEDDING_MAX_BATCH_CHUNKS_HARD_CAP` (64), and
`RAG_EMBEDDING_MAX_BATCH_TOKENS_HARD_CAP` (50,000) bound execution. Optional
`RAG_EMBEDDING_MAX_INFLIGHT_REQUESTS`, `RAG_EMBEDDING_BATCH_MAX_CHUNKS` and
`RAG_EMBEDDING_BATCH_TARGET_TOKENS` supply custom-profile defaults; empty values
inherit defaults. Select `custom` to retain explicit legacy tuning for new items.

Provider connection/model `config_json` may set `embedding_speed_profile`,
`max_inflight_requests`, `max_batch_chunks`, `max_batch_tokens`,
`retry_max_attempts` and `retry_delay_seconds`. Model settings cannot lift a
connection ceiling. Workspace preferences cannot lift provider/host ceilings.
SentenceTransformer, Ollama and token-hash execution use one inflight batch, with
CPU/GPU batch ceilings. Increasing burst may encounter more rate limits; API
cost depends primarily on embedded data/tokens.

Workspace AI exposes Tiết kiệm, Cân bằng, Nhanh, Tùy chỉnh and inheritance.
`GET /workspaces/{id}/embedding-runtime` returns the effective policy and limits.
`PATCH` requires `ai.change_embedding`; custom values above the effective ceiling
are rejected. Model identity/bindings remain independent of speed preferences.

Batch layout stays fixed across resume; inflight limits are checked again on each
delivery. If a host lowers batch hard caps below an existing layout, processing
fails before calling the provider. Drain work before lowering these caps, or
restore the previous cap to resume it.

## Progress and retries

Progress advances through PARSING 20, CHUNKING 45, EMBEDDING 65–84, INDEXING 85–99,
READY 100. Completed chunk counts come from checkpoint rows, including batches
that finish out of order. Retry/resume keeps the stage, percentage and completed
chunks. Explicit retry of failed durable work resets its retry budget and reuses
the manifest/checkpoints. Fresh reindex or failed work without a durable manifest
starts a new processing lifecycle.

Document list/detail return `work_state`, `waiting_reason`, `retry_at`,
`embedded_chunks` and `total_chunks`. Provider 429 respects numeric Retry-After
(clamped to 2–120 seconds). Defaults allow eight attempts per failed batch/finalize
operation and at most 48 quota waits; authentication/configuration/invalid-vector
errors are not automatically retried. Advisory locks protect work item and
document through checkpoint commits and redeliveries.

UI displays chunk counts and wait explanations/countdowns. Active documents poll
every three seconds; waiting-only lists poll after at most ten seconds or near
the earliest retry time. Polling stops when all documents are READY/FAILED.

## Verification

From `backend/`:

```sh
python -m pytest -p no:cacheprovider tests/test_embedding_fastpath.py
python -m pytest -p no:cacheprovider tests/test_embedding_handoff_integration.py
python scripts/benchmark_embedding_execution.py --out ../artifacts/embedding-execution-benchmark.json
```

The integration test needs disposable `RAGHUB_TEST_DATABASE_URL`. It uses fresh
sessions and real advisory locks/checkpoints with deterministic provider/storage/
index adapters: a successful batch, 429 with Retry-After 3, resume of only the
failed batch, then READY. The benchmark simulates latency for OpenAI-compatible,
Gemini-like, SentenceTransformer and Ollama execution. It measures scheduling,
not live API performance or hardware throughput. Live provider benchmarking
remains an installation-specific validation.

The [controlled benchmark report](../artifacts/embedding-execution-benchmark.json)
records one run against the same 192-chunk manifest for all policies.

Telemetry includes batches, latency, inflight deltas, rate limits, retries,
checkpoint resumes, cache hit ratio and document duration, with low-cardinality
provider/profile/result labels. No document content or credentials are logged.

Adaptive concurrency and SSE remain P2 work.
