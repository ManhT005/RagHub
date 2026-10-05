# RagHub Core public API

This contract is frozen before the physical package move, after syncing
`origin/develop` at `854dcaf`. Moving imports changes the namespace, not engine
behavior, constructor dependencies, commands, results or transaction policy.
The canonical engine namespace is `raghub_core`; `app` owns hosts and adapters.

## Stable entry points

Host composition must import supported public use cases from `raghub_core.api`.
Direct imports of `raghub_core.application` and its submodules in composition are
forbidden by the architecture gate. Concrete adapters
implement protocols in `raghub_core.ports`. Domain modules remain available for
typed values used by these protocols; internal algorithm helpers are not facade
exports. The initial backend wheel contains both packages and retains its existing
`raghub-backend` distribution name/version.
A standalone, independently versioned `raghub-core` distribution is intentionally
**Deferred**; see [ADR-001](adr/ADR-001-core-package-boundary.md).

The supported facade is exactly the following 27 exports. Adding or removing a
symbol requires an intentional contract update in `tests/core/test_public_api.py`.
The facade re-exports original symbols without wrappers or constructor changes.

| Group | Facade exports |
| --- | --- |
| Documents | `UploadDocumentUseCase`, `RetryDocumentUseCase`, `UploadDocumentCommand`, `UploadReceipt` |
| Ingestion | `BuildDocumentIndexUseCase`, `RunIngestionUseCase`, `ReindexWorkspaceUseCase` |
| Retrieval | `RetrieveContextUseCase`, `RetrievalScope`, `RetrievedChunk`, `ContextBundle` |
| RAG | `StreamRagChatUseCase`, `StreamChatCommand`, `RagEvent`, `ConversationStarted`, `CitationsResolved`, `TokenDelta`, `UsageReported`, `ChatCompleted`, `ChatFailed` |
| Chatbots | `ManageChatbotUseCase`, `PublishChatbotUseCase`, `ChatbotConfig`, `ChatbotRecord`, `CreateChatbotCommand`, `PatchChatbotCommand` |
| Errors | `CoreError` |

Repository implementations, storage/search/queue adapters, routers, credentials,
database sessions and concrete provider HTTP clients are excluded from the facade.

| Entry point | Operation | Injected dependencies |
| --- | --- | --- |
| `UploadDocumentUseCase` | `await execute(UploadDocumentCommand) -> UploadReceipt` | document repository, async object storage, task queue; default size limit 25 MB |
| `RetryDocumentUseCase` | `await execute(scope, version_id, reindex=False) -> UploadReceipt` | retry repository and task queue |
| `BuildDocumentIndexUseCase` | `await execute(document, resolve_embedding, make_store, ...) -> DocumentIndex` | async storage, parser, chunker; callbacks for stages/index exposure |
| `RunIngestionUseCase` | `await execute(version_id, retries=0, max_retries=3) -> IngestionResult` | ingestion repository, shared index builder, provider resolver, vector-store factory |
| `ReindexWorkspaceUseCase` | `await execute(job_id, fail_transient=False)` | reindex repository, the same index builder, provider resolver, vector-store factory |
| `RetrieveContextUseCase` | `await retrieve(scope, query, limit) -> list[RetrievedChunk]`; `await execute(...) -> ContextBundle` | provider resolver, readiness filter, vector-search factory |
| `StreamRagChatUseCase` | `execute(StreamChatCommand) -> AsyncIterator[RagEvent]` | chatbot reader, retrieval, providers, conversations, usage recorder; optional timing factory |
| `ManageChatbotUseCase` | `list`, `get`, `create`, `update`, `delete` | chatbot repository and publication use case |
| `PublishChatbotUseCase` | `await execute(record, published=True) -> ChatbotRecord` | chatbot repository and provider resolver |

Factory parameters are callables supplied by a host; the application never
constructs a concrete adapter. Synchronous vector-index/task-queue protocol methods
keep their existing signatures during this move. Object storage remains async.

## Commands and domain values

Values listed below that are absent from the facade export table are domain/port
contracts for adapters, imported from their canonical modules.

- `UploadDocumentCommand`: organization/workspace UUIDs, filename, content type
  and bytes. `UploadReceipt` preserves document/version/job UUIDs, status and timestamp.
- `StreamChatCommand`: organization/chatbot UUIDs, question, optional conversation
  UUID and external-user ID. The chatbot supplies the trusted workspace scope.
- `RetrievalScope`: generic organization/workspace UUIDs, with no role or host mode.
- `CreateChatbotCommand` and `PatchChatbotCommand`: preserve existing defaults and
  explicit unset semantics. `ChatbotConfig`/`ChatbotRecord` carry detached state.
- `IngestionDocument`, `IngestionAttempt`, `IngestionResult`, `DocumentIndex`,
  `IndexedChunk`, `RetrievedChunk` and `ContextBundle`: typed pipeline data.
- `ChatMessage`, `ChatOptions`, `ChatStreamDelta`, `ChatUsage`, `TrustedCitation` and
  `ChatUsageRecord`: provider and RAG contracts. `ProviderDescriptor` is detached,
  deeply immutable and excludes decrypted credentials.

## Streaming events

Successful ordering is:

```text
ConversationStarted -> CitationsResolved -> TokenDelta* -> UsageReported -> ChatCompleted
```

| Event | Payload |
| --- | --- |
| `ConversationStarted` | conversation UUID and durable user-message UUID |
| `CitationsResolved` | tuple of trusted citations from retrieved source metadata |
| `TokenDelta` | text |
| `UsageReported` | `ChatUsage` |
| `ChatCompleted` | assistant-message UUID, optional first-token milliseconds, latency milliseconds |
| `ChatFailed` | stable error code and safe message |

After a conversation starts, handled generation/retrieval failures end in
`ChatFailed` and persist the failed assistant turn. Validation/authorization
failures before that point raise `CoreError`. Cancellation retains the policy in
[RAG conversation transactions](RAG_CONVERSATION_POLICY.md). Hosts alone serialize
events into SSE, CLI output or other transports.

## Ports

The supported protocol set is:

| Module | Contracts |
| --- | --- |
| `object_storage` | `ObjectStoragePort`: async `put`, `get`, `remove` |
| `parsing` | `DocumentParserPort`: synchronous `parse` to parsed sections |
| `vector_store` | `VectorSearchPort`, `VectorStorePort` |
| `provider_resolver` | `ProviderResolverPort`, `EmbeddingRuntime`, `ChatRuntime` |
| `task_queue` | `TaskQueuePort` |
| `documents` | `DocumentRepositoryPort`, `DocumentRetryRepositoryPort` |
| `ingestion`, `reindex` | `IngestionRepositoryPort`, `ReindexRepositoryPort` |
| `retrieval` | `DocumentReadinessPort`, `RetrievalPort` |
| `conversations` | `ConversationRepositoryPort` |
| `chatbots` | `ChatbotReadPort`, `ChatbotRepositoryPort` |
| `usage` | `UsageRecorderPort` |

Repositories enforce the supplied scope and own persistence mechanics. The engine
controls documented commit points through these contracts. Redis admission,
authentication, origin handling and distributed task locks belong to hosts.

## Errors and preserved behavior

`CoreError(code, message, details=None)` carries no HTTP status. Existing codes
include `WORKSPACE_NOT_FOUND`, `DOCUMENT_VERSION_NOT_FOUND`, `CHATBOT_NOT_FOUND`,
`CHATBOT_NOT_PUBLISHED`, `STORAGE_UNAVAILABLE`, `QUEUE_UNAVAILABLE`,
`SEARCH_UNAVAILABLE`, `PROVIDER_TIMEOUT`, `PROVIDER_UNAVAILABLE`,
`PROVIDER_AUTH_FAILED`, `PROVIDER_RATE_LIMITED`, `PROVIDER_INVALID_RESPONSE`,
`PROVIDER_NOT_CONFIGURED`, `PROVIDER_DISABLED` and `CHAT_RUNTIME_FAILED`.
Upload validation and document retry retain their existing validation/status codes.
`IngestionError` retains its separate `code` and `retryable` contract and the existing
retryable-error policy. HTTP status mappings and additional delivery-only codes
stay in `app.delivery.http.error_mapping`.

The move preserves extension/MIME/size validation, SHA-256, immutable document
versions, retry limits, stage transitions, failed-index cleanup and READY semantics.
Retrieval preserves organization/workspace isolation, READY filtering, hybrid RRF,
context budget and trusted metadata. Reindex preserves model/dimension snapshots
and validation before switching the active index. Empty-context chat skips the
provider, submitted questions are committed before AI work, previous history is
loaded before adding that question, and streaming preserves TTFT/latency and native
or estimated usage. Adapters do not retry after the first token. Chatbot management
retains existing permissive publication semantics; explicit publication can use
the stricter readiness gate.

No parser formats, reranker, OCR, RBAC redesign or deployment-mode conditions are
introduced by package consolidation.
