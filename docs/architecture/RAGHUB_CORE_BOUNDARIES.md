# RagHub Core boundaries

RagHub Core is the reusable knowledge and RAG engine. The current product is an
owner-operated, self-hosted RagHub instance. Cloud/SaaS and enterprise governance
remain future work; no deployment mode, platform role or billing policy enters the
engine. Instance authorization belongs at the delivery boundary; organization
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

This refactor was rebuilt from current `origin/develop` (`8c1c5ef`) on
`refactor/core-selfhost-v1`, porting the earlier core commits individually. This
baseline includes workspace RBAC, public chat, embed keys, origin policy, Redis
admission, the widget, and current GHCR/CI workflows.

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

`SelfHostContainer`, `PublicChatContainer`, and `WorkerContainer` wire those ports
to the existing adapters for their respective hosts.
`modules/*/service.py` retains compatibility facades. HTTP uploads stop at
`delivery/http/uploads.py`; typed RAG events become SSE only in
`delivery/http/sse.py`. Celery task names and arguments remain unchanged.

`ProviderDescriptor` contains deeply immutable, detached options and no credentials.
The persistence mapper selects the embedding index snapshot before registry
construction. Decrypted credentials are passed separately to the factory.

## Platform authorization versus engine scope

The instance keeps existing `ADMIN` / `WORKSPACE_ADMIN` authorization. Delivery
authenticates and authorizes a request before creating an engine command. The
engine has no platform role enum, billing state or deployment mode. Its
repositories still enforce the command's organization/workspace scope,
and the RAG runtime verifies the resolved chatbot belongs to that organization.

`delivery/security/public_chat.py` resolves the published embed key to the chatbot
and its active workspace on the server. Browser tenant IDs are ignored. Origin
checks compare explicit HTTP(S) scheme/host/port and reject paths, credentials and
wildcards. Redis rate limits and concurrency leases remain outside the core.

Public chat calls `PublicChatContainer.stream_events`; authenticated Playground
uses the `ChatbotService.stream_events` facade over `SelfHostContainer`. Both use
the same `StreamRagChatUseCase`. `delivery/http/public_chat.py` adds the public
deadline, observability and shielded lease cleanup around the shared SSE adapter.
Cleanup covers completion, provider failure, timeout, disconnect and serialization
failure. The core never imports Redis or serializes SSE.

The existing authenticated API keeps its permissive `published` flag semantics.
`PublishChatbotUseCase.execute` provides the stricter configuration/provider
readiness gate for a control plane that chooses to enable it. The existing embed
publication, appearance settings and key rotation retain their HTTP behavior.

## Migration and invariants

Each step is a separate reviewable commit: inventory; pure primitives; ports;
ingestion and reusable indexing; retrieval; typed RAG runtime and SSE adapter;
chatbot domain; ORM-free provider registry; delivery cleanup; contract suite.
Compatibility imports preserve pure primitive/provider class identity. Legacy
HTTP `AppError` is now a delivery subclass of the transport-free `CoreError`;
HTTP delivery selects the status using `delivery/http/error_mapping.py`.

Preserve existing routes, SSE payloads and workspace authorization. Preserve 25 MB
validation, MIME/extension checks, SHA-256, immutable document versions, three
retries, pinned concurrent-delivery locks, index cleanup, READY-only retrieval,
organization/workspace filtering, embedding snapshots/dimensions, trusted
citations, empty-context provider bypass, no retry after first token, TTFT,
latency and native/fallback usage.

The application explicitly loads previous history and appends the submitted
question, commits the question before AI work, and records failed assistant turns
using existing message metadata. See [conversation transaction policy](RAG_CONVERSATION_POLICY.md)
for successful, failed and cancelled turns. Membership lifecycle is now scoped to
the organization by migration `20261003_0012`; an organization administrator cannot
disable or reactivate a global identity. This control-plane change stays outside
the engine.

Retrieval fusion, context budgeting and citation resolution consume typed
`RetrievedChunk` objects. Raw Elasticsearch hit mapping belongs to infrastructure;
compatibility dictionaries remain in outer facades only. Object storage methods are
async; the MinIO adapter runs blocking SDK calls in a thread. Services expose typed
RAG events, and only HTTP delivery maps events to SSE payloads. Redis admission lives
in `infrastructure/redis/public_chat_admission.py`, with HTTP dependencies in
`delivery/public/admission.py`.

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
| CORE-8 | Current public chat uses the shared typed RAG runtime; server scope, explicit origins and Redis admission remain in delivery |
| CORE-9 | HTTP maps inputs/results; Celery tasks delegate bootstrap and use cases; compatibility paths retained |
| CORE-10 | Core-only CI, fake-port contracts, dependency tests and separate live integration tests implemented |

The [self-host verification report](../operations/SELF_HOST_VERIFICATION.md) records
current core-only, backend, UI, migration and operations evidence. The isolated
adapter suite includes PostgreSQL concurrency, conversation persistence, public
SSE, Redis admission and workspace rebuilds. A separate CPU self-host installation
exercises actual Sentence Transformer and Ollama models, restart persistence and
backup/restore into a new project. Core contracts still require neither Docker nor
model downloads. Full pull-request CI remains necessary before merge into `develop`.
