# RAG operations runbook

## Feature flags (all default off except the prompt budget)

| Flag | Default | Enable | Rollback |
|---|---|---|---|
| `RAG_RELEVANCE_GATE_ENABLED` | `false` | After calibration + holdout pass; `shadow → 10% → 50% → 100%` internal canary | Set `false`: instant return to top-k, no reindex |
| `RAG_RERANKER_ENABLED` | `false` | After p95 ≤ 750 ms and quality gates; independent canary | Set `false`: fusion output continues |
| `RAG_OCR_ENABLED` | `false` | After resource/security test per MIME | Per-adapter off; indexed docs stay until reindex |
| `RAG_INDEX_GC_ENABLED` | `false` | After 7-day dry-run audit with zero false positives | Disable apply, keep dry-run |
| `RAG_EMBEDDING_CACHE_ENABLED` | `false` | After tenant/fingerprint isolation verification | Set `false`; durable work-item checkpoints still apply |
| `RAG_NEIGHBOR_EXPANSION_ENABLED` | `false` | After same-document quality/latency comparison | Set `false`; no reindex |
| `RAG_ADAPTIVE_CLARIFICATION_ENABLED` | `false` | After reviewed uncertainty-policy evaluation | Set `false`; configured pre-retrieval policy continues |
| Prompt budgeter | always on | Safety boundary; roll back via model registry/config | `RAG_MAX_OUTPUT_TOKENS` / `RAG_PROMPT_SAFETY_MARGIN` |
| Provider binding | live | Roll back binding to prior pool/profile | If fingerprint differs from active index, roll back the active index version too |

## Threshold calibration

Run backend commands below from `backend/`, with the deployment's configured
DB/search/provider settings. Fixture `rag_golden_eval.py` is a lexical comparison
tool and must not train a production gate.

1. In a dedicated evaluation workspace, disable the relevance gate, neighbor
   expansion and both workspace-provider/local reranking while collecting fused
   scores. Use `python scripts/collect_calibration_scores.py --mint-email <eval-email>
   --out ../artifacts/calib_scores.json` after ingesting the original golden corpus.
   This collector uses HTTP search results; verify they are unmodified fused scores
   and match the runtime five-candidate feature window. Non-default pipelines need
   an equivalent collector before calibration.
2. `python scripts/calibrate_relevance.py --scores <calibration-scores>.json \
   --out artifacts/relevance_<version>.json --dataset-hash <qa-hash> \
   --config-hash <retrieval-hash> --fingerprint <active-embedding-fingerprint> \
   --version <version>`
   Collector output may contain both splits; the calibrator selects only
   `calibration`. A list explicitly containing holdout rows is rejected.
3. Evaluate the 10 holdout cases; never tune the threshold on holdout.
4. Deploy the artifact path via `RAG_RELEVANCE_ARTIFACT_PATH` and set
   `RAG_RELEVANCE_CONFIG_VERSION`. A dataset/config hash mismatch keeps the
   gate off automatically. Fingerprint mismatch also keeps it off. Compute hashes
   with `app.modules.search.relevance.dataset_hash` and `retrieval_config_hash`,
   using the same QA file, candidates, RRF k, mapping version and document cap as
   `app.composition.retrieval`. Report hashes from other eval scripts are not
   interchangeable with artifact hashes.

## Upgrade and worker routing

Back up the database, retained index versions and object storage before upgrading
a deployed installation. `python -m alembic upgrade head` reaches revision `0030`.
The migration graph reconciles develop's `0021/0022` and legacy RAG `0026` histories;
do not rename deployed revisions manually. Test upgrades covered all three histories
(including an empty DB) and retained existing organization data.

The normal worker consumes `celery`, `rag-ingestion`, `rag-reindex` and
`rag-embedding`. When `RAG_OCR_ENABLED=true`, ingestion/reindex jobs route entirely
to `rag-ocr`; launch the Compose `ocr` profile as well. Its worker concurrency is
one. This also limits non-OCR ingestion in that deployment; increasing the number
of OCR workers increases the aggregate CPU load.

For a local build, use `docker build --target ocr -t raghub-ocr -f backend/Dockerfile .`
from the repo root; `ocr-local-ai` adds the local AI dependencies. GHCR deployments
use the OCR image tag configured by their Compose example. API and worker settings
must agree about OCR enablement. Validate the image from the repository root:

```powershell
Get-Content -Raw backend/scripts/verify_ocr_runtime.py | docker run --rm -i raghub-ocr python -
```

Queue caps use `PROVIDER_POOL_MAX_ACTIVE_JOBS_PER_WORKSPACE` and
`PROVIDER_POOL_MAX_PENDING_JOBS_PER_WORKSPACE`. Durable manifests/vector batches
live in object storage. Resume by retrying the existing document/job with the same
target fingerprint/index; do not discard checkpoints to work around quota waits.

## Local reranker preparation

Prepare using an environment with the local AI dependencies installed:

```text
python scripts/prepare_reranker.py --directory <deployment-snapshot-directory>
python scripts/measure_rerank.py --organization-id <eval-org-uuid> --workspace-id <eval-workspace-uuid>
```

Review the pinned revision and prepared files/checksum before deployment. Mount
the snapshot read-only, set `RAG_RERANKER_SNAPSHOT_PATH` to its container path and
`RAG_RERANKER_EXPECTED_SHA256` to the approved printed checksum. Runtime never
downloads weights. Keep `RAG_RERANKER_ENABLED=false` until baseline comparisons and
hardware-specific p95 measurements pass. Workspace-provider reranking remains
independently configured; it takes precedence over this local fallback.

## Semantic support review and draft data

The [V2 draft](../backend/tests/fixtures/rag_golden_v2/README.md) has 210 generated
variants in 30 families and zero reviewed V2 labels. Keep it separate from the
original baseline until source/fact links and missing format coverage are reviewed.

Live reports retain each answer and its `citation_inventory`. Reviewer annotations
are a JSON object keyed by case ID. Example entry:

```json
{
  "case-id": {
    "answer_sha256": "<SHA-256 of the exact UTF-8 answer>",
    "expected_facts": [{"fact": "cost", "supporting_chunk_ids": ["<actual-chunk-id>"]}],
    "observed_facts": [{
      "fact": "cost",
      "claim_text": "<exact claim text, including its citations>",
      "cited_chunk_ids": ["<actual-chunk-id>"]
    }]
  }
}
```

Inspect source text to verify each expected support link. Record all answer claims,
including unsupported ones using an unmatched fact label; link citation markers
to the actual inventory chunk IDs. The tool measures reviewer labels; it does not
judge semantic equivalence automatically. Missing/stale reviews or uncited claims
without a measurable precision leave the aggregate support metric unavailable.
Reviews cover answerable cases without provider errors; provider errors are gated
separately. Fixture aliases such as `doc-001:p1:c0` need mapping to actual chunks.

```text
python scripts/score_fact_support.py --report <live-report.json> --annotations <review.json> --out <reviewed-report.json> --gate --thresholds <thresholds.json>
```

Threshold overrides are a JSON metric-to-number map, for example:

```json
{"mrr@5": 0.70, "ndcg@5": 0.75, "answerable_hit@5": 0.85, "retrieval_p95_ms": 300}
```

Semantic scoring recomputes the verdict and preserves thresholds from the input
report unless explicitly overridden; stale verdicts are removed. Its defaults
require support precision ≥ 0.90 and fact support recall ≥ 0.85 in addition to the
base production runner gates. Exit code 2 means missing review or a failed enabled
gate. Citation ID precision and lexical `facts_recall` remain separate metrics.
Nightly lexical comparison is informational; it does not establish production
quality. TTFT/rerank release thresholds and reviewed live evidence remain pending.

## Quality gates

Retrieval hit@5 ≥ 0.85, MRR@5 ≥ 0.70, nDCG@5 ≥ 0.75; rejection F1 ≥ 0.90;
citation precision = 1.00, coverage and faithfulness ≥ 0.90; no metric more
than 0.02 below the approved baseline. Retrieval p95 ≤ 300 ms without
reranker, ≤ 750 ms with it.

## Versioned reindex and rollback

1. Stage a new `EmbeddingIndexVersion` (new mapping or fingerprint).
2. Reindex, then validate count/dimension/sample queries/golden.
3. Activate only on pass; the previous active id is returned for rollback.
4. Roll back with the retained version inside its retention window:
   repoint the workspace active pointer; never edit a live mapping in place.
5. Uploads in flight keep their target-index snapshot; a target change
   supersedes and reschedules them.

## Index GC recovery

- Default is dry-run: `python -m app.cli index-gc` prints decisions and writes
  audit rows without deleting.
- Protected: active index, pending/running jobs, work-item workspaces, two
  newest completed versions per workspace. Retired kept ≥ 24 h, failed 7 days.
- Deleted indices recover from snapshot or reingest only; retention is a hard
  precondition for `--apply`.

## Contract and release

- `python scripts/export_openapi.py --out docs/api/openapi.json`
- `python scripts/build_postman_collection.py --openapi docs/api/openapi.json \
  --out postman/collections/raghub-api.postman_collection.json`
- CI regenerates both into temp dirs and fails on diff.
- `POSTMAN_ENV=/tmp/seed-env.json bash postman/run.sh` runs the collection
  locally (newman); seed via `backend/scripts/seed_contract_env.py` against
  an ephemeral stack. No paid provider in PR gates; no secrets leave the runner.
