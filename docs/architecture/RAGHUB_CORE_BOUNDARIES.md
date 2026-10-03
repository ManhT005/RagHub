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

The baseline dependency map was:

```text
DocumentService -> UploadFile + MinIO + SQLAlchemy repository + Celery task
workers -> parsing/chunking + ProviderResolver + MinIO + Elasticsearch + ORM
SearchService -> ProviderResolver + Elasticsearch + ORM readiness query
ChatbotService -> CRUD + retrieval + provider resolution + conversation/usage ORM
ProviderRegistry -> SQLAlchemy ProviderConfig
```

## Extracted engine entry points

| Capability | Application entry point | Dependencies |
| --- | --- | --- |
| Upload | `application/documents/upload_document.py` | DocumentRepositoryPort, ObjectStoragePort, TaskQueuePort |
| Retry / document reindex | `application/documents/retry_document.py` | DocumentRetryRepositoryPort, TaskQueuePort |
| Ingestion | `application/ingestion/run_ingestion.py` | IngestionRepositoryPort, provider resolver, index builder |
| Parse/chunk/embed/index | `application/ingestion/build_document_index.py` | Parser callable, ObjectStoragePort, embedding runtime, VectorStorePort |
| Workspace rebuild | `application/ingestion/reindex_workspace.py` | ReindexRepositoryPort and the same index builder |
| Retrieval/context | `application/retrieval/retrieve_context.py` | ProviderResolverPort, VectorSearchPort, DocumentReadinessPort |
| Streaming RAG | `application/rag/stream_chat.py` | ChatbotReadPort, RetrievalPort, ProviderResolverPort, ConversationRepositoryPort, UsageRecorderPort |
| Chatbot CRUD/publication | `application/chatbots/*` | ChatbotRepositoryPort and provider readiness contracts |

`composition/*` and `delivery/workers/*` wire those ports to the existing adapters.
`modules/*/service.py` retains compatibility facades. HTTP uploads stop at
`delivery/http/uploads.py`; typed RAG events become SSE only in
`delivery/http/sse.py`. Celery task names and arguments remain unchanged.

`ProviderDescriptor` contains deeply immutable, detached options and no credentials.
The persistence mapper selects the embedding index snapshot before registry
construction. Decrypted credentials are passed separately to the factory.

## Platform authorization versus engine scope

Cloud membership roles and enterprise identity/SSO policies can differ. Their
delivery adapters must authenticate and authorize a request before creating an
engine command. The engine has no platform role enum, billing state or deployment
mode. Its repositories still enforce the command's organization/workspace scope,
and the RAG runtime verifies the resolved chatbot belongs to that organization.

For a future public widget, the delivery adapter must resolve scope from the public
chatbot identity on the server. It must never construct scope from browser-supplied
tenant IDs. Origin checks, rate limits and concurrency leases belong to that wrapper.

The existing authenticated API keeps its permissive `published` flag semantics.
`PublishChatbotUseCase.execute` provides the stricter configuration/provider
readiness gate for a control plane that chooses to enable it. Public integration
readiness has no implementation to validate in this baseline.

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

For a core-only environment, install `backend/requirements-core-test.lock` rather
than the backend runtime dependencies, then run `python -m pytest -p
no:cacheprovider tests/core` from `backend/`. CI has a separate job using that
minimal dependency set. Adapter tests stay outside `tests/core`.

## Extraction status and verified limits

| Plan stage | Status |
| --- | --- |
| CORE-0 / CORE-1 | Inventory, canonical pure packages, PDF adapter and compatibility imports implemented |
| CORE-2 | Typed ports wired into the existing adapters; fake adapters exercised by contract tests |
| CORE-3 | Upload/ingestion/rebuild callable without Celery; initial and rebuild indexing share one use case |
| CORE-4 | Retrieval callable without concrete Elasticsearch dependencies; READY and tenant filters preserved |
| CORE-5 | Typed streaming events, prompt/citation policies, conversation/usage ports and SSE adapter implemented |
| CORE-6 | Chatbot management separated; publication readiness gate explicit and opt-in for existing HTTP behavior |
| CORE-7 | Registry imports without ORM/settings; immutable descriptor and shared provider contract tests implemented |
| CORE-8 | Not applicable to existing functionality: public runtime is absent |
| CORE-9 | HTTP maps inputs/results; Celery tasks delegate bootstrap and use cases; compatibility paths retained |
| CORE-10 | Core-only CI, fake-port contracts, dependency tests and separate live integration tests implemented |

Verified locally: 220 backend tests passed, including nine live integration tests;
lint passed. The 50 core tests also passed in a Python environment without FastAPI,
ORM, worker, storage/search SDKs or PyMuPDF. Live coverage includes ingestion and
PostgreSQL concurrency, chatbot CRUD and empty-context authenticated SSE, and a
workspace rebuild changing embedding dimension from 384 to 128 while retaining
the document version and switching the active index.
The backend wheel includes the bundled tokenizer and its core imports independently
of the runtime dependencies.

Live tests used an isolated Docker project and local token-hash embeddings. Shared
provider tests mock vendor I/O and the local sentence-transformer model. This does
not claim a live Gemini/OpenAI/Ollama/model-download or public-widget deployment
test, nor a completed Cloud/Enterprise control plane.
