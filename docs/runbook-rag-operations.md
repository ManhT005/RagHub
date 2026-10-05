# RAG operations runbook

## Feature flags (all default off except the prompt budget)

| Flag | Default | Enable | Rollback |
|---|---|---|---|
| `RAG_RELEVANCE_GATE_ENABLED` | `false` | After calibration + holdout pass; `shadow → 10% → 50% → 100%` internal canary | Set `false`: instant return to top-k, no reindex |
| `RAG_RERANKER_ENABLED` | `false` | After p95 ≤ 750 ms and quality gates; independent canary | Set `false`: fusion output continues |
| `RAG_OCR_ENABLED` | `false` | After resource/security test per MIME | Per-adapter off; indexed docs stay until reindex |
| `RAG_INDEX_GC_ENABLED` | `false` | After 7-day dry-run audit with zero false positives | Disable apply, keep dry-run |
| Prompt budgeter | always on | Safety boundary; roll back via model registry/config | `RAG_MAX_OUTPUT_TOKENS` / `RAG_PROMPT_SAFETY_MARGIN` |
| Provider binding | live | Roll back binding to prior pool/profile | If fingerprint differs from active index, roll back the active index version too |

## Threshold calibration

1. Collect retrieval scores on the 20 calibration cases only:
   `python scripts/rag_golden_eval.py --out artifacts/scores.json`
   (score export shape documented in the eval report).
2. `python scripts/calibrate_relevance.py --scores <calibration-scores>.json \
   --out artifacts/relevance_<version>.json --dataset-hash <qa-hash> \
   --config-hash <retrieval-hash> --version <version>`
3. Evaluate the 10 holdout cases; never tune the threshold on holdout.
4. Deploy the artifact path via `RAG_RELEVANCE_ARTIFACT_PATH` and set
   `RAG_RELEVANCE_CONFIG_VERSION`. A dataset/config hash mismatch keeps the
   gate off automatically.

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
