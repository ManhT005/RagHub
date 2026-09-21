# Phase-one API

All vertical-slice routes are below `/api/v1`. Until authentication is added in
phase two, requests must pass the organization UUID through `X-Organization-ID`.
The header is a temporary development scope and is not an authentication control.

## Upload PDF

`POST /api/v1/workspaces/{workspace_id}/documents`

Send `multipart/form-data` with one `file` field. A successful request returns
`202 Accepted` with document, version and ingestion-job IDs.

## Search chunks

`GET /api/v1/workspaces/{workspace_id}/search?q=...&limit=5`

The Elasticsearch query always filters by the organization header and workspace
path before BM25 ranking. Results contain source, page and stable chunk IDs.

## Health

- `GET /health/live` checks the API process.
- `GET /health/ready` checks PostgreSQL, Redis, Elasticsearch and MinIO.
