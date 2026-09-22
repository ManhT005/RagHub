# Phase-two API

All routes are below `/api/v1`. Protected routes require an `Authorization:
Bearer <access-token>` header. Organization-scoped routes also require
`X-Organization-ID`; the authenticated user must be a member of that organization.

## Authentication

- `POST /auth/register` and `POST /auth/login` accept `email` and `password`,
  return an access token, and set the HTTP-only `refresh_token` cookie.
- `POST /auth/refresh` rotates the access token from that cookie.
- `POST /auth/logout` clears the cookie.
- `GET /auth/me` returns the current authenticated user.

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

Send `multipart/form-data` with one `file` field. PDF with selectable text,
UTF-8 TXT, and UTF-8 Markdown are accepted, up to `MAX_UPLOAD_SIZE_MB` (25 MB by
default). Upload requires `OWNER`, `ADMIN`, or `EDITOR`. A successful request
returns `202 Accepted` with `document_id`, `document_version_id`, `job_id`, and
`status: "QUEUED"`. The original filename is normalized and used only as
metadata; the object key is generated from UUIDs.

`GET /workspaces/{workspace_id}/documents` lists non-deleted documents with
`status`, `stage`, `progress`, `attempts`, `error_code`, `error_message`, and
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

The Elasticsearch query always filters by the authorized organization and
workspace path before BM25 ranking. Results contain source, page and stable
chunk IDs, plus heading metadata where available. The current `EMBEDDING`
stage creates deterministic 384-dimensional token-hash vectors locally. These
vectors provide a stable index contract; they are lexical features and should
be replaced by a semantic model before semantic vector search is offered.

## Health

- `GET /health/live` checks the API process.
- `GET /health/ready` checks PostgreSQL, Redis, Elasticsearch and MinIO.
