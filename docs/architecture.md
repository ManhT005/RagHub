# Phase-one and phase-two architecture

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

## Public chat boundary

The public chatbot router is an access gateway around the existing RAG chat service. A
`public_key` resolves one published chatbot, and the backend derives its organization and
workspace; public request bodies cannot supply either value. Browser traffic is checked against
the chatbot's canonical origin allowlist, while traffic without an `Origin` requires a
chatbot-scoped API key stored as an HMAC digest.

Before an SSE response starts, Redis atomically applies a fixed-window chatbot/IP rate limit and
acquires a sorted-set lease at chatbot and organization scope. The stream generator releases both
lease memberships in `finally`; scores and key TTLs provide crash recovery. Redis guard failures
fail closed. The gateway then delegates retrieval, citations, persistence, provider streaming and
usage accounting to `ChatbotService.stream`, preserving the existing tenant filters and SSE
contract.

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
