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
- `GET`/`POST /workspaces` list or create workspaces in the header organization.
- `GET`/`PATCH`/`DELETE /workspaces/{workspace_id}` read, update, or soft-delete
  a workspace. `VIEWER` is read-only; only `OWNER`/`ADMIN` may delete.

## Upload PDF

`POST /api/v1/workspaces/{workspace_id}/documents`

Send `multipart/form-data` with one `file` field. A successful request returns
`202 Accepted` with document, version and ingestion-job IDs.

`GET /workspaces/{workspace_id}/documents` lists non-deleted documents and
their current ingestion status. `DELETE /workspaces/{workspace_id}/documents/{document_id}`
soft-deletes a document; it requires `OWNER`, `ADMIN`, or `EDITOR`.

## Search chunks

`GET /api/v1/workspaces/{workspace_id}/search?q=...&limit=5`

The Elasticsearch query always filters by the authorized organization and
workspace path before BM25 ranking. Results contain source, page and stable
chunk IDs.

## Health

- `GET /health/live` checks the API process.
- `GET /health/ready` checks PostgreSQL, Redis, Elasticsearch and MinIO.
