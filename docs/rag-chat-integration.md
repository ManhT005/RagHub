# RAG chat integration

The integrated chat path now enforces the following backend-owned sequence:

1. Resolve the workspace embedding index and run scoped hybrid retrieval.
2. Validate candidate document and document-version state in PostgreSQL.
3. Build a token-bounded context and retain exactly the included hits.
4. Resolve trusted citation metadata from those included hits.
5. Stream chat deltas, usage, and completion timing through SSE.

Embedding and chat providers remain independent workspace bindings. Changing the chat provider
does not stage an embedding re-index; changing the embedding configuration continues to use the
versioned index workflow.

## SSE contract

A successful grounded response emits events in this order:

```text
conversation
citations
token (one or more)
usage
done
```

`done.first_token_ms` measures provider time-to-first-token. It starts immediately before
`stream_chat()` and excludes retrieval, context construction, and conversation history loading.
`usage.source` is `provider` when native counts are available and `estimated` otherwise.

When retrieval returns no valid context, chat provider resolution and invocation are skipped. The
stream still follows the contract with an empty citation list, the fixed fallback answer, zero
usage with source `none`, and a `done` event whose `first_token_ms` is null.

If the provider fails after streaming starts, the terminal event is `error`. The backend does not
retry after the first token, emit `done`, or persist a completed assistant message.

## Database migration

Apply the first-token metric migration before running the updated API:

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
```

The new nullable column is `usage_events.first_token_ms`.

## Automated verification

```powershell
cd backend
..\.venv\Scripts\python.exe -m ruff check app tests
..\.venv\Scripts\python.exe -m pytest
```

Integration tests requiring Docker are marked and may be skipped by a unit-test-only environment.

## External smoke test

Set the following host environment variables. Base URLs must be public HTTP(S) endpoints accepted
by provider URL validation.

```powershell
$env:RAGHUB_EXTERNAL_EMBEDDING_BASE_URL = 'https://provider.example/v1'
$env:RAGHUB_EXTERNAL_EMBEDDING_MODEL = 'embedding-model'
$env:RAGHUB_EXTERNAL_EMBEDDING_DIMENSION = '1536'
$env:RAGHUB_EXTERNAL_EMBEDDING_API_KEY = '<secret>'
$env:RAGHUB_EXTERNAL_CHAT_BASE_URL = 'https://provider.example/v1'
$env:RAGHUB_EXTERNAL_CHAT_MODEL = 'chat-model'
$env:RAGHUB_EXTERNAL_CHAT_API_KEY = '<secret>'

.\scripts\rag-chat-smoke.ps1 -Mode External `
  -ResultPath .\artifacts\rag-external-result.json
```

The script never includes secrets in its result. Use `-DocumentPath` and `-Question` to validate a
specific real document; otherwise it creates a temporary UTF-8 text fixture.

## Local smoke test

Build the backend with local sentence-transformer dependencies and start Ollama:

```powershell
$env:BACKEND_IMAGE_TARGET = 'local-ai'
$env:OLLAMA_MODEL = 'gemma3:1b'

docker compose -f infrastructure/docker-compose.yml --profile local-ai up --build -d --wait

.\scripts\rag-chat-smoke.ps1 -Mode Local `
  -ResultPath .\artifacts\rag-local-result.json
```

Optional overrides are `RAGHUB_LOCAL_EMBEDDING_MODEL`,
`RAGHUB_LOCAL_EMBEDDING_DIMENSION`, and `RAGHUB_OLLAMA_BASE_URL`. The Ollama URL must be reachable
from the API container; its default is `http://ollama:11434`.

## Sprint gate evidence

Each smoke result records the git commit, mode, workspace, provider/model identities, document,
question, retrieved and cited chunk IDs, token counts, first-token latency, total latency, and
PASS status. Citation chunk IDs are checked against scoped retrieval results before PASS is emitted.

The Sprint 5 gate is open only after both result files are produced by real executions:

- `RAG-E2E-01`: External mode PASS.
- `RAG-E2E-02`: Local mode PASS.

Do not commit provider keys or reports containing environment-specific identifiers unless the
project explicitly requires those artifacts to be retained.
