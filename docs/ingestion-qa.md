# Ingestion QA follow-up

Retested on 2026-09-22 against the findings for `c57b4f6` in
`RagHub_Ingestion_Task_Report.md`.

| Finding | Resolution | Regression coverage |
| --- | --- | --- |
| DEF-ING-001 | TXT paragraphs stay in one citation section and are merged by the chunker. | Short paragraphs produce chunks of 80–450 tokens; short documents and page/heading boundaries are preserved. |
| DEF-ING-002 | Worker holds a PostgreSQL session advisory lock on a pinned connection throughout processing and failure recording. | Two concurrent worker entries on independent PostgreSQL connections execute the pipeline once, including across stage commits. |
| DEF-ING-003 | Retry locks the scoped version/job rows and claims a transaction advisory lock before resetting the job. | Two concurrent requests enqueue exactly one task; a finishing worker prevents a new retry claim. |
| DEF-ING-004 | Manual retry accepts only storage, queue, embedding and index unavailability codes. | PDF/OCR/decode errors are rejected; cross-tenant retry returns 404. |
| DEF-ING-005 | Terminal versions are checked under the worker lock before updating attempts. | READY/FAILED redelivery makes no mutations; a real READY redelivery preserves attempts. |
| DEF-ING-006 | `chunk_index` is global within the document version. | Multi-page and multi-heading documents have sequential indexes and retain citations. |
| DEF-ING-007 | Worker/API store or expose safe messages, and the UI maps known codes to user messages. Raw exception details remain in logs. | API and UI tests verify internal hostnames and credentials are not displayed. |
| DEF-ING-008 | Token hashing is explicitly documented as a development stub. | Semantic model/provider integration remains part of the retrieval phase. |

Additional regressions cover exact 25 MiB and 25 MiB + 1 byte, Windows filename
normalization, Markdown code fences (including mixed or shorter fences), and
positive OWNER/ADMIN/EDITOR authorization.

## Local verification

- 46 backend unit/HTTP tests passed.
- 6 PostgreSQL concurrency/retry tests passed using independent connections.
- 1 live HTTP → MinIO → Celery → PostgreSQL → Elasticsearch test passed for
  PDF/TXT/Markdown, permanent failure, manual retry rejection, and tenant scope.
- Ruff passed; Angular tests passed (3 tests) and production build passed.
- Alembic upgrade from an empty QA database passed; `alembic check` reported
  no new upgrade operations.

The existing local `raghub` database contains two indexes not declared by the
repository migrations (`ix_ingestion_jobs_document_version_id` and
`ix_organizations_slug`). Its drift check reports those extras. Verification on
the fresh `raghub_ingestion_qa_20260922` database confirms the migration/model
contract is consistent; the existing database was not altered to remove them.

## Running the integration gates

Start API/worker and their dependencies using Docker Compose. Set:

```text
RAGHUB_TEST_BASE_URL=http://localhost:8000
RAGHUB_TEST_DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/<database>
```

From `backend`, run `python -m pytest -p no:cacheprovider -m integration`.
The database must have `alembic upgrade head` applied. PostgreSQL concurrency
fixtures remove only their own generated organizations; the live HTTP test
creates uniquely named QA accounts/workspaces/documents.

CI already includes Ruff, pytest, Angular test/build, and migration checks.
An `Ingestion integration` job now starts the real services and runs the live
and concurrency regressions with both variables set, so these tests are not
silently skipped in that job. Remote CI/PR status has not been executed or
certified in this local run; the report's G9 remains pending.
