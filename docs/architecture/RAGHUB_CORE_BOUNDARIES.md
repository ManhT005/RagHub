# RagHub Core boundaries

RagHub Core is the reusable knowledge and RAG engine. Cloud SaaS, enterprise,
private and local deployments compose the same engine with different adapters.
Platform administration, identity provisioning, billing and deployment are outside
the engine. Platform authorization belongs at the delivery boundary; organization
and workspace isolation remains mandatory inside every data operation.

## Dependency direction

```text
HTTP / worker delivery -> application -> core_domain + ports
infrastructure / persistence / AI adapters -> core_domain + ports
composition roots -> concrete adapters + application
```

`app/core_domain` is the engine's domain, algorithms, policies and contracts.
`app/application` owns workflows. `app/ports` defines their external dependencies.
The existing `app/core` is legacy runtime support (FastAPI authentication, settings,
database, logging and middleware), **not RagHub Core**. Keeping that distinction
avoids moving runtime dependencies into the reusable engine.

Core and application must not import FastAPI, Celery, SQLAlchemy, Redis, MinIO,
Elasticsearch, vendor HTTP clients, settings or concrete adapters. CPU libraries
such as tiktoken are allowed. PDF decoding with PyMuPDF is an adapter; text and
Markdown parsing and section/chunk contracts belong to the core.

## Baseline inventory

| Existing location | Classification | Extraction |
| --- | --- | --- |
| `modules/ingestion/parser.py` | CORE + PDF ADAPTER | Pure TXT/Markdown parser; PDF adapter |
| `modules/ingestion/chunker.py`, `tokenizer.py`, `errors.py` | CORE | Ingestion primitives and errors |
| `modules/ingestion/embedder.py` | Compatibility stub | Removed production entry point |
| `modules/search/hybrid.py` | CORE | RRF, token budget, context bundle |
| `modules/chatbots/citations.py`, `timing.py` | CORE | Trusted citations and timing |
| `modules/ai_providers/contracts.py`, `errors.py`, `enums.py`, `usage.py` | CORE | Provider contracts, errors, usage |
| `modules/ai_providers/adapters/*`, `policy.py` | ADAPTER | Provider I/O, retry, timeouts |
| `modules/ai_providers/registry.py` | ADAPTER / composition | Construct from an ORM-free descriptor |
| `modules/ai_providers/resolver.py` | PERSISTENCE ADAPTER | Resolve bindings and index snapshots |
| `modules/ai_providers/crypto.py` | ADAPTER | Credential encryption |
| `modules/documents/service.py` | APPLICATION + DELIVERY + ADAPTER | Upload command, storage and queue ports |
| `modules/documents/repository.py` | PERSISTENCE ADAPTER | Document and ingestion persistence |
| `modules/search/service.py` | APPLICATION + ADAPTER | Retrieval use case and readiness adapter |
| `modules/chatbots/service.py` | APPLICATION + ADAPTER + DELIVERY | CRUD, publication, RAG runtime, persistence |
| `modules/chatbots/provider.py` | ADAPTER / compatibility | Legacy Gemini provider wrapper |
| `modules/ai_providers/service.py` | CONTROL PLANE + ADAPTER | Provider management and index bindings |
| `modules/*/models.py`, `app/models.py` | PERSISTENCE ADAPTER | SQLAlchemy entities and registration |
| `modules/*/schemas.py` | DELIVERY | HTTP validation and response contracts |
| `modules/*/router.py`, `app/main.py` | DELIVERY / composition | HTTP auth, command/result mapping |
| `modules/auth`, `users`, `memberships`, `organizations`, `workspaces` | CONTROL PLANE | Identity, roles, tenant provisioning |
| `modules/health/router.py` | DELIVERY + ADAPTER | Runtime dependency health checks |
| `infrastructure/object_storage/minio.py` | ADAPTER | ObjectStoragePort |
| `infrastructure/elasticsearch/chunks.py` | ADAPTER | Vector search and indexing ports |
| `infrastructure/task_queue/celery_app.py` | ADAPTER / composition | Broker configuration |
| `infrastructure/ingestion_lock.py` | ADAPTER | Pinned PostgreSQL ingestion lock |
| `workers/tasks.py`, `workers/reindex_tasks.py` | DELIVERY + APPLICATION + ADAPTER | Move pipeline ownership to use cases |
| `core/*` | Runtime support / DELIVERY / ADAPTER | Keep outside engine boundary |
| `apps/admin-web`, `infrastructure/docker*`, `.github` | CONTROL PLANE / deployment | Outside the engine |

Package `__init__.py` files are namespace markers and take the classification of
their containing package. Alembic is persistence/deployment tooling.

## Migration and invariants

Each step is a separate reviewable commit: inventory; pure primitives; ports;
ingestion and reusable indexing; retrieval; typed RAG runtime and SSE adapter;
chatbot domain; ORM-free provider registry; delivery cleanup; contract suite.
Compatibility imports preserve class/function identity for existing consumers.

Keep routes, SSE payloads, database schema and RBAC unchanged. Preserve 25 MB
validation, MIME/extension checks, SHA-256, immutable document versions, three
retries, pinned concurrent-delivery locks, index cleanup, READY-only retrieval,
organization/workspace filtering, embedding snapshots/dimensions, trusted
citations, empty-context provider bypass, no retry after first token, TTFT,
latency and native/fallback usage.

The checked-out baseline has authenticated chat only. Public keys, origin policy,
Redis rate/concurrency limiting and a public widget are not existing capabilities.
CORE-8 cannot be validated as an extraction here; adding those features is a
separate change. A future public delivery adapter must call the same typed RAG
runtime, derive tenant scope server-side and release concurrency leases on every
exit path.

## Verification

Run backend checks from `backend/`:

```powershell
../.venv/Scripts/python.exe -m ruff check .
../.venv/Scripts/python.exe -m pytest -p no:cacheprovider -m 'not integration'
```

Core contract tests use fake ports and no Docker or network. Infrastructure
integration tests remain marked `integration` and require the existing stack.
Architecture tests enforce dependency direction, including transitive imports.
