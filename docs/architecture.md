# Demo architecture

Angular -> FastAPI -> SQLAlchemy repository -> SQLite.
File UUID -> BackgroundTasks -> parse PDF/UTF-8 -> page-aware chunks (260 words, overlap 40) -> READY.
BM25 retrieves only READY documents in owner + workspace scope. SSE events: citations, token, done.
Citations come from retrieved chunks, never invented by a model.

## Modules

- core/database: demo persistence and schema initialization.
- core/security: scrypt passwords and hashed opaque tokens.
- modules/repository: scoped data access.
- modules/ingestion: parsing and chunking.
- modules/search: lexical retrieval.
- main: HTTP composition. Split into domain routers/services as scope grows.

## Roadmap to the supplied MVP design

1. Normalize data into PostgreSQL models + Alembic; organizations, memberships and RBAC.
2. MinIO storage, Celery/Redis ingestion, durable jobs and document versions with idempotency.
3. EmbeddingProvider, Elasticsearch versioned index, mandatory tenant/workspace filters, vector + BM25 + RRF.
4. ChatProvider adapters for OpenAI-compatible endpoints and Ollama, encrypted secrets, provider streaming and usage.
5. JWT/refresh rotation, distributed limits, audit, expanded parsers and security tests.
6. NG-ZORRO, Angular routing, TypeScript widget, browser E2E and CI.

Compose intentionally runs only the implemented API and Angular/Nginx. Infrastructure adapters above are not implemented yet.

References: https://angular.dev/reference/versions and https://fastapi.tiangolo.com/tutorial/background-tasks/ .
