# Phase-two API

All routes are below `/api/v1`. Protected routes require an `Authorization:
Bearer <access-token>` header. Organization-scoped routes also require
`X-Organization-ID`; the authenticated user must be a member of that organization.

## Authentication

- `POST /auth/login` authenticates an existing local identity. Public
  registration and third-party login are disabled; accounts must be provisioned
  administratively.
- `POST /auth/password/forgot` always returns the same `202` response and emails
  a one-time reset link when the account exists. `POST /auth/password/reset`
  consumes that link; `POST /auth/password/change` requires authentication and
  the current password.
- `POST /auth/refresh` rotates an opaque refresh token stored only as a hash in
  `user_sessions`. Reuse of a revoked refresh token revokes all user sessions.
- `POST /auth/logout` revokes the current session and clears the cookie.
- `GET /auth/me` returns the current authenticated user.

SMTP uses `smtp.gmail.com:587` with STARTTLS. `SMTP_PASSWORD` must be a Google
App Password. In development, missing SMTP configuration uses a log sender; in
non-development environments all SMTP settings are required at startup.

## Organizations and workspaces

- `POST /organizations` creates an organization and makes its creator `OWNER`.
- `GET /organizations` lists organizations available to the current user.
- `GET /organizations/{id}/members` lists members; `PUT` to the same path adds
  or changes a registered user's role. Only `OWNER` and `ADMIN` may do this.
- `DELETE /organizations/{id}/members/{user_id}` removes a non-owner member;
  it also requires `OWNER` or `ADMIN`.
- `GET`/`POST /workspaces` list or create workspaces in the header organization.
- `GET`/`PATCH`/`DELETE /workspaces/{workspace_id}` read, update, or soft-delete
  a workspace. `VIEWER` is read-only; only `OWNER`/`ADMIN` may delete.

## Document ingestion

`POST /api/v1/workspaces/{workspace_id}/documents`

Send `multipart/form-data` with one `file` field. PDF (text-first with
table extraction and optional Tesseract OCR `vie+eng`), UTF-8 TXT, UTF-8
Markdown, DOCX, sanitized HTML (never fetches external resources) and XLSX
(read-only, data-only, no macros) are accepted, up to `MAX_UPLOAD_SIZE_MB`
(25 MB by default). Preflight rejects files over 25 MB compressed, 100 MB
decompressed, 70 PDF pages, 50 OCR pages, 80.000 tokens, 250 chunks,
macro-enabled containers and signature mismatches before embedding. Upload requires `OWNER`, `ADMIN`, or `EDITOR`. A successful request
returns `202 Accepted` with `document_id`, `document_version_id`, `job_id`, and
`status: "QUEUED"`. The original filename is normalized and used only as
metadata; the object key is generated from UUIDs.

`GET /workspaces/{workspace_id}/documents` lists non-deleted documents with
`status`, `stage`, `progress`, `embedded_chunks`, `total_chunks`,
`queue_position`, `attempts`, `error_code`, `error_message`, and
`retryable`. Error messages are safe descriptions mapped from error codes;
provider exceptions appear only in server logs.
Stages are `QUEUED`, `PARSING`, `CHUNKING`, `EMBEDDING`, `INDEXING`, `READY`, and
`FAILED`. Transient storage and index errors receive up to three automatic
retries. Invalid input and unsupported OCR do not retry automatically.

`POST /workspaces/{workspace_id}/document-versions/{version_id}/retry` resets a
failed version's job and returns the same `202 Accepted` response shape. It
requires `OWNER`, `ADMIN`, or `EDITOR` and does not create a new version.
Only `STORAGE_UNAVAILABLE`, `QUEUE_UNAVAILABLE`, `EMBEDDING_UNAVAILABLE`, and
`INDEX_UNAVAILABLE` can be retried. Invalid PDFs, unsupported OCR and text
decoding failures require a corrected upload (`409 DOCUMENT_NOT_RETRYABLE`).
Concurrent retries are serialized with row locks, and ingestion uses a
PostgreSQL advisory lock held across stage commits. Redelivery of a READY
version leaves attempts and status unchanged.

`DELETE /workspaces/{workspace_id}/documents/{document_id}` soft-deletes a
document; it requires `OWNER`, `ADMIN`, or `EDITOR`.

## Search chunks

`GET /api/v1/workspaces/{workspace_id}/search?q=...&limit=5`

Retrieval is hybrid BM25 + vector kNN fused with RRF (`k=60`, 25 candidates
per branch by default). The Elasticsearch mapping `vi_hybrid_v2` keeps the
exact `content` field plus a folded `content.folded` analyzer for
diacritic-insensitive Vietnamese, with heading (`2.0`) and source-name
(`1.2`) boosts. Tenant and `retrievable` filters apply inside every branch
before the cutoff; the database `READY` filter remains as defense in depth.
Results contain source, page and stable chunk IDs, plus heading metadata
where available. Query embeddings must match the active index fingerprint;
changing the embedding profile triggers a versioned reindex.

## RAG Chat

- `GET`/`POST` `/workspaces/{workspace_id}/chatbots`, `GET`/`PATCH`/`DELETE` `/chatbots/{chatbot_id}` manage organization-scoped chatbots. Writers create or modify them; all organization members can read them.
- `POST /chatbots/{chatbot_id}/chat` requires a published chatbot and returns `text/event-stream`. Events are `conversation`, `citations`, zero or more `token`, then `done`; failures are `error`. Citations are derived from the request retrieval hits, never from model-generated text. Every prompt is capped by a global token budget (system + question never cut; history newest pairs up to 25%; context fills the rest); citations mirror exactly the sent slices and answers must use `[Cn]` markers.
- Out-of-scope questions hit the relevance gate (default off until calibrated) or the empty-context fallback; both emit no fake citations.
- Set `GEMINI_API_KEY` in the server environment. The backend uses Gemini's OpenAI-compatible streaming endpoint; credentials never reach the client. Workspaces bind managed provider pools, never API keys.

## Health

- `GET /health/live` checks the API process.
- `GET /health/ready` checks PostgreSQL, Redis, Elasticsearch and MinIO.
