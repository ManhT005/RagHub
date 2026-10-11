# HaUI active-v1 question bank

This is a 28-case draft benchmark for the 15 documents currently active in the
`HaUI Assistant` workspace (snapshot: 2026-10-09). It deliberately excludes
soft-deleted documents and duplicate versions.

The file is not a release-quality golden set yet. An initial mapping from each
answerable case to actual active-index chunk UUIDs is in
`artifacts/haui_active_v1_evidence.auto.json`. It is suitable for a first
retrieval run, but a domain reviewer should confirm it before a release gate.
Each entry corresponds to the chunk(s) shown in the Admin chat source panel
(C1, C2, ...):

```json
{
  "ug-001": ["actual-chunk-uuid"],
  "master-005": ["actual-chunk-uuid-a", "actual-chunk-uuid-b"]
}
```

Only then can the retrieval metrics be computed against real chunks, e.g.:

```bash
python scripts/run_retrieval_ablation.py \
  --organization-id <organization-uuid> \
  --workspace-id <workspace-uuid> \
  --qa tests/fixtures/benchmark/haui_active_v1/questions.json \
  --evidence-map artifacts/haui_active_v1_evidence.auto.json \
  --out ../artifacts/haui_active_v1_retrieval.json
```

`questions.json` is intentionally not passed directly to
`run_production_eval.py`: that runner expects a self-contained corpus manifest
and reviewed reference facts. After review, promote this bank by adding
`expected_facts`, `supporting_chunk_ids`, and a corpus manifest snapshot.
