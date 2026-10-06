# Phase-one and phase-two architecture

For the reusable engine boundary and extraction status, see
[RagHub Core boundaries](architecture/RAGHUB_CORE_BOUNDARIES.md).

The repository has two Python projects: `raghub-core` contains the reusable engine
under `src/raghub_core`; `backend` contains its self-host host and concrete adapters
under `app`. The backend package depends on core and the engine never imports the
host. Composition uses `raghub_core.api` and adapters implement core ports.
See [ADR-001](architecture/adr/ADR-001-core-package-boundary.md) and the
[package refactor verification](architecture/RAGHUB_CORE_SIBLING_VERIFICATION.md).

RagHub starts as a modular monolith plus a background worker. The API and worker
share domain models and infrastructure adapters while running as separate
processes.

```text
Browser -> Nginx -> Angular Admin
                 -> FastAPI -> PostgreSQL
                            -> MinIO
                            -> Redis -> Celery worker -> MinIO
                                                    -> PostgreSQL
                                                    -> Elasticsearch
                 -> FastAPI search ----------------> Elasticsearch
```

## Vertical slice

1. The upload endpoint verifies organization/workspace scope, PDF MIME/extension
   and the configured size limit.
2. The API calculates SHA-256, stores the original under a UUID-based MinIO key,
   creates document/version/job rows, then enqueues only the version ID.
3. The worker downloads the object, parses pages with PyMuPDF and chunks each
   page independently so citation metadata is never crossed.
4. Stable chunk IDs are derived from the document version, page and chunk index.
5. The worker creates the versioned Elasticsearch index and alias if needed,
   replaces chunks for that document version, then marks metadata `READY`.
6. Search always applies both organization and workspace filters before BM25
   ranking.

Phase one intentionally does not create embeddings. Vector search and RRF are
added in phase three without changing the upload, parser or storage boundaries.

## Identity and tenant boundary

Phase two introduces `users` and `memberships`. Access tokens identify a user;
the refresh token is stored only as an HTTP-only cookie. An organization-scoped
request carries `X-Organization-ID`, which is authorized against the user's
membership before the router calls document, workspace, or search services.

Roles are `OWNER`, `ADMIN`, `EDITOR`, and `VIEWER`. Authorization is enforced
at the API boundary; repositories still apply organization and workspace filters
to protect retrieval and document data isolation.

## RAG pipeline upgrade (evaluation-first)

- Golden corpus and QA live in `backend/tests/fixtures/rag_golden/` (hash-locked,
  offline). The eval runner `backend/scripts/rag_golden_eval.py` calls the same
  application use cases as production and reports hit@5/MRR/nDCG, rejection F1,
  citation precision/coverage and faithfulness.
- Providers are managed pools: workspaces bind profiles, credentials stay
  platform-side. Embedding fingerprint v2 covers type/endpoint/model/dimension;
  failover never crosses fingerprints. Quota buckets (Redis rolling RPM/TPM/RPD)
  gate every external embedding call; ingestion embeds at most 24 chunks/~10K
  tokens per batch with per-batch checkpoints and resume.
- Retrieval fuses 25 BM25 + 25 vector candidates (RRF k=60) over the
  `vi_hybrid_v2` mapping, with an optional calibrated relevance gate and a
  local cross-encoder reranker (both default off, independent flags).
- Prompts obey a global token budget; citations mirror sent slices and answers
  use `[Cn]` markers validated post-stream as a release gate.
- Telemetry records stage timings with low-cardinality labels only; GC runs
  dry-run by default (`python -m app.cli index-gc`, `--apply` requires
  `RAG_INDEX_GC_ENABLED`).
- API compatibility is frozen by `docs/api/openapi.json` and the Postman
  collection in `postman/`; CI regenerates both into temp dirs and diffs.

## Error contract

Application and validation errors use one envelope:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "request_id": "uuid",
    "details": {}
  }
}
```
