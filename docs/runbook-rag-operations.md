# RAG operations runbook

## Acceptance scope

The October 6 optimization iteration prioritizes reliable operations: bounded
resource use, queue fairness, recoverable work, safe publication and observable
failures. Local model quality and latency depend on the configured model and
hardware; they are diagnostic results, not mandatory acceptance thresholds for
this iteration. Reviewed 200?300-case data is not required to finish this scope.
Evaluation tools enforce thresholds only when explicitly requested with `--gate`.

Run Python commands below from `backend/`, with the installation's configured
DB/search/broker/provider settings. Run Docker commands from the repository root.

## Feature flags

| Flag | Default | Enable after | Rollback |
|---|---|---|---|
| `RAG_RELEVANCE_GATE_ENABLED` | `false` | Matching calibration artifact and reviewed refusal behavior | Set `false`; no reindex |
| `RAG_RERANKER_ENABLED` | `false` | Preparing the pinned local snapshot and checking available capacity | Set `false`; fusion continues |
| `RAG_ADAPTIVE_RERANK_ENABLED` | `false` in custom profile | Checking confidence routing; CPU/GPU presets may enable routing | Set `false`; configured reranking continues |
| `RAG_EVIDENCE_SELECTION_ENABLED` | `false` | Comparing evidence coverage and prompt fit | Set `false`; no reindex |
| `RAG_OCR_ENABLED` | `false` | Resource/security checks per MIME and an OCR worker | Disable; indexed documents remain |
| `RAG_INDEX_GC_ENABLED` | `false` | Dry-run audit of retention and protected versions | Disable apply; keep dry-run |
| `RAG_EMBEDDING_CACHE_ENABLED` | `false` | Tenant/fingerprint isolation checks | Set `false`; durable checkpoints remain |
| `RAG_NEIGHBOR_EXPANSION_ENABLED` | `false` | Checking same-document evidence and context budget | Set `false`; no reindex |
| `RAG_ADAPTIVE_CLARIFICATION_ENABLED` | `false` | Reviewing uncertainty policy | Set `false`; configured policy continues |
| `RAG_TELEMETRY_JSON_ENABLED` | `false` | Configuring JSON log capture for API and workers | Set `false`; ordinary logging continues |
| Prompt budgeter | Always on | Fixed prompts/question, then evidence, then bounded history | Adjust context/output/safety configuration |

Adaptive reranking skips inference only for calibrated HIGH confidence. MEDIUM
and unknown confidence keep the configured reranker; LOW can reject retrieval.
A mismatched artifact produces unknown confidence. Reranker failure falls back
to fused evidence. Enabling adaptive routing does not install or enable a model.

## Capacity presets and queue routing

`RAG_HARDWARE_PROFILE=custom` preserves explicit settings. Opt-in presets are
starting configurations, not throughput or quality guarantees:

| Profile | Worker concurrency | Candidates | Rerank source/top count | Active jobs/workspace |
|---|---:|---:|---:|---:|
| `lite_cpu` | 1 | 15 | 12 / 5 | 1 |
| `standard_cpu` | 1 | 25 | 20 / 6 | 1 |
| `gpu` | 2 | 40 | 40 / 8 | 2 |

Use the selected hardware profile from `.env.self-host`:

```sh
docker compose \
  --env-file .env.self-host \
  -f infrastructure/docker-compose.self-host.yml \
  --profile local-ai \
  up -d
```

Presets: `RAG_HARDWARE_PROFILE=lite_cpu` (default), `standard_cpu`, or `gpu`.
Explicit configuration in the env file overrides preset defaults. Empty values
fall back to the selected preset.

Workload isolation separates user-facing ingestion from long-running model operations:
- The RAG worker (`worker`) consumes `rag-ingestion`, `rag-embedding` and `rag-reindex`.
  Its concurrency defaults to the hardware preset (1 on CPU, 2 on GPU).
- The dedicated provider worker (`worker-provider`) consumes `rag-provider` and `celery`
  at concurrency 1, handling downloads, Ollama pulls and fail-fast health probes without
  starving document uploads.
- With `RAG_OCR_ENABLED=true`, ingestion/reindex route to `rag-ocr` on the `worker-ocr`
  service (start with `--profile ocr`).
Queue caps use `PROVIDER_POOL_MAX_ACTIVE_JOBS_PER_WORKSPACE` and
`PROVIDER_POOL_MAX_PENDING_JOBS_PER_WORKSPACE`.

The provider worker's `celery` subscription is temporary migration compatibility
for provider messages queued before the split. TODO(provider-queue-migration):
remove it after all supported installations have upgraded and drained the legacy
backlog; new provider tasks route exclusively to `rag-provider`.

OCR routing remains a coarse host-level switch and defaults to disabled.
TODO(ocr-routing): escalate only documents requiring OCR after parsing to
`rag-ocr`, instead of routing every ingestion/reindex when OCR is enabled.

Run the model-free starvation regression from `backend/` against disposable
PostgreSQL and Redis services (set `RAGHUB_TEST_DATABASE_URL` and
`RAGHUB_TEST_REDIS_URL`):

```sh
python -m pytest -p no:cacheprovider tests/test_rag_worker_starvation.py
```

The test starts two real Celery consumers with the production routes and a busy
provider task, then requires `documents.ingest_version` to finish within five
seconds before releasing the provider. It exercises the ingestion lock and DB
transitions with a test pipeline; it does not download models or validate real
embedding/indexing. Queues are namespaced and DB entities use an isolated schema.

Native local inference retains its capacity slot until the underlying thread
finishes, even if the caller cancels. Document token limits are checked before
full chunk allocation/provider resolution, and chunk count is bounded.

## Upgrade, durable resume and publication

Back up deployed databases, retained indices and object storage before upgrading.
`python -m alembic upgrade head` reaches revision `0030`. The migration graph
reconciles develop's `0021/0022` and legacy RAG `0026` histories. Empty, develop and
legacy RAG database upgrades were tested; do not rename deployed revisions.

Durable manifests and vector batches live in object storage. Resume the existing
document/job with the same target fingerprint/index. Checkpoint storage outages
are retryable; a vector artifact already written before an interrupted response
is reused. Explicit document retry resets FAILED work for the active target index
and preserves completed batches. Quota waits do not justify deleting checkpoints.

Before replacement, publication validates chunk IDs, vector keys, dimensions and
finite values. Count verification precedes publication, and retrieval readiness
excludes uncommitted evidence. Changing provider binding to a different embedding
fingerprint also requires a matching active index version.

The versioned document pipeline defaults to `legacy`. Configure
`providerOptions.document_pipeline` as `normalized-v1` or `context-v1` when creating
a new index configuration; runtime reads `config_json.document_pipeline`.
Normalization retains raw citation text/offsets and structural metadata. The
context pipeline embeds deterministic source/section/page context. Pipeline
changes alter the fingerprint and require a new index/reindex; do not edit a live
index configuration in place.

## Model-free operations snapshot

```text
python scripts/capture_rag_operations.py --out ../artifacts/rag_ops.json
python scripts/capture_rag_operations.py --out ../artifacts/rag_ops.json --telemetry <saved-json.log>
```

These commands read DB work-item/ingestion states and broker queue depths without
calling AI models. Optional telemetry summarizes stage count/p50/p95, counters
and cache hit rate over the supplied log window. Missing infrastructure is listed
in `issues`; `--strict-infrastructure` opts into failure exit status. Queue depth
is a point-in-time snapshot, not a throughput measurement. An undeclared empty
queue reports zero; other broker failures remain visible.

Set `RAG_TELEMETRY_JSON_ENABLED=true` consistently on API/workers and restart them
to emit JSON events. Labels are sanitized and exclude document/question content;
the operations summary omits correlation IDs. Cache counters include duplicate
chunks, cache hits/misses, estimated tokens saved and avoided embedding calls.
Token savings use a tokenizer proxy, not provider billing. Percentiles use
nearest-rank selection, including the higher sample for a two-sample p95.

The checked-in [operations smoke report](../artifacts/optimization-operations-smoke.json)
comes from a disposable empty DB/broker stack. It verifies diagnostic plumbing;
it does not establish loaded throughput, model quality or hardware performance.

## Retrieval diagnostics and calibration

```text
python scripts/run_retrieval_ablation.py --organization-id <UUID> --workspace-id <UUID> --qa <QA.json> --out ../artifacts/retrieval_ablation.json
python scripts/rag_dataset_audit.py --qa <QA.json>
```

Ablation runs actual BM25/ANN queries for each candidates/RRF/document-cap cell
and reuses query embeddings. Unlike the operations snapshot, it calls the
configured embedding provider. It records pipeline/fingerprint/mapping/schema,
context tokens and measured latency; it does not automatically change runtime
settings. Add `--evidence-map <mapping.json>` for reviewed case-ID to actual chunk
UUID lists. Without labels, quality metrics are unavailable and the report is
not release eligible. Dataset audit is informational; `--gate` opts into reviewed
family/format/split checks.

Collect calibration directly from ready fused top-five candidates, before
reranking, gating and neighbor expansion:

```text
python scripts/collect_calibration_scores.py --organization-id <UUID> --workspace-id <UUID> --qa <QA.json> --out ../artifacts/calib_scores.json
python scripts/calibrate_relevance.py --scores ../artifacts/calib_scores.json --out ../artifacts/relevance_v3.json --version <version>
```

The collector records dataset/config hashes, embedding fingerprint, mapping
version and `fused-ready-top5-v3` feature schema. The calibrator imports that
metadata; manual identity overrides must match. It trains only `calibration`
rows; holdout rows never train the threshold. Evaluate holdout independently.
Fixture lexical comparisons must not train a production relevance gate.

Deploy with `RAG_RELEVANCE_ARTIFACT_PATH` and `RAG_RELEVANCE_CONFIG_VERSION`.
Runtime currently hashes `backend/tests/fixtures/rag_golden/qa.json`; a custom QA
artifact cannot activate unless that runtime dataset identity matches. Any
identity/schema mismatch disables calibrated gating. Report hashes from other
evaluation tools are not interchangeable with artifact hashes.

## Local model preparation

```text
python scripts/prepare_reranker.py --directory <snapshot-directory>
python scripts/measure_rerank.py --organization-id <UUID> --workspace-id <UUID>
```

Use an environment with local AI dependencies. Review the pinned revision and
checksum, mount the snapshot read-only, then configure
`RAG_RERANKER_SNAPSHOT_PATH` and `RAG_RERANKER_EXPECTED_SHA256`. Runtime never
downloads reranker weights. Workspace-provider reranking takes precedence over
the local fallback. Choose enablement based on deployment capacity and observed
behavior; this iteration does not require a fixed local latency threshold.

For OCR, build from the repository root:

```text
docker build --target ocr -t raghub-ocr -f backend/Dockerfile .
```

`ocr-local-ai` also includes local AI dependencies. Validate the built image:

```powershell
Get-Content -Raw backend/scripts/verify_ocr_runtime.py | docker run --rm -i raghub-ocr python -
```

## Optional answer quality review

The [V2 draft](../backend/tests/fixtures/rag_golden_v2/README.md) has 210 generated
variants in 30 families and zero reviewed V2 labels. It remains draft data; it is
not evidence of 200 independent reviewed cases or production answer quality.

Live reports retain exact answers and citation inventories. Reviewer annotations
are keyed by case ID, for example:

```json
{
  "case-id": {
    "answer_sha256": "<SHA-256 of the exact UTF-8 answer>",
    "expected_facts": [{"fact": "cost", "supporting_chunk_ids": ["<actual-chunk-id>"]}],
    "observed_facts": [{
      "fact": "cost",
      "claim_text": "<exact claim including citations>",
      "cited_chunk_ids": ["<actual-chunk-id>"]
    }]
  }
}
```

Review all cases without provider errors, including unanswerable cases. Record
all claims and unsupported ones using unmatched labels. A reviewed refusal can
have an empty observed-fact list. Verify source/fact links against actual text;
fixture aliases need mapping to runtime UUIDs. Missing/stale answer hashes leave
support metrics unavailable and remove stale verdicts.

Precision/fact support recall aggregate answerable cases; unsupported claim rate
also includes claims in unanswerable responses. Grounding and citation correctness
are separate: a claim supported elsewhere in the provided inventory can have a
low unsupported rate while its inline citation is wrong.

```text
python scripts/score_fact_support.py --report <live-report.json> --annotations <review.json> --out <reviewed-report.json>
```

Completed-review scoring is diagnostic by default. Missing review/support
precision returns exit code 2 even without a gate; this optional reviewer tool
is not required for operational acceptance. Add
`--gate --thresholds <thresholds.json>` only for a selected evaluation gate. Defaults then include support
precision 0.90, fact support recall 0.85 and unsupported claim rate at most 0.10,
alongside production-runner thresholds. `--require-reviewed-v2` is a separate
opt-in check. A requested metric with missing evidence fails an enabled gate.

Live runner TTFT measures client time until the first SSE token; server generation
first-token time is recorded separately. Backoff/retry time contributes to total
latency, and a response is never retried after its first token. Provider/service
errors are counted separately from false rejection/answer rates. Operator-supplied
HTTP runtime configuration is labeled as supplied, not claimed as verified.

Reference targets such as hit@5 0.85, MRR@5 0.70, nDCG@5 0.75 or retrieval p95
300/750 ms may guide a later deployment benchmark. They are not mandatory gates
for this operations iteration and do not override model/hardware constraints.

## Versioned reindex, rollback and GC

1. Stage a new index version for a changed mapping/fingerprint/pipeline.
2. Reindex and verify counts, dimensions, readiness and representative queries.
3. Activate after verification; retain the previous active version for rollback.
4. Roll back by repointing to a retained version; never modify a live mapping.
5. In-flight uploads keep their target snapshot; target changes supersede/reschedule them.

GC defaults to dry-run: `python -m app.cli index-gc` records decisions without
deleting. Active versions, pending/running work and the two newest completed
versions per workspace are protected. Retired versions remain at least 24 hours;
failed versions remain seven days. Audit retention before `--apply`; deleted
indices require snapshot restoration or reingestion.

## API contracts

```text
python scripts/export_openapi.py --out ../docs/api/openapi.json
python scripts/build_postman_collection.py --openapi ../docs/api/openapi.json --out ../postman/collections/raghub-api.postman_collection.json
```

CI regenerates both into temporary directories and checks differences. Contract
runs use a seeded ephemeral stack; no paid provider is required for PR checks.
