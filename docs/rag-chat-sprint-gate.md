# RAG chat Sprint 5 gate report

## Gate status

| Gate | Result |
|---|---|
| RAG-E2E-01 External | PASS |
| RAG-E2E-02 Local | PASS |
| True SSE through Nginx | PASS |
| Local regression | PASS |
| GitHub CI / reviews | PENDING |
| Sprint 5 | READY (all local & E2E smoke gates passed; pending GitHub CI / reviews) |

## RAG-E2E-01 External evidence

| Field | Value |
|---|---|
| Execution Date | 2026-09-27T09:33:20.2475147+00:00 |
| Git Commit | `b34301f2622b4cef9fc9dd5496b4c7893ad29f51` |
| Mode | External |
| Workspace | `86f31825-556b-4618-a167-94424884e888` |
| Embedding Provider | `GOOGLE_GEMINI` |
| Embedding Model | `gemini-embedding-2` |
| Chat Provider | `GOOGLE_GEMINI` |
| Chat Model | `gemini-3.5-flash-lite` |
| Document | `f3bca8d5-93a8-4a2f-8348-98d7b64ba927` |
| Question | What is the RagHub smoke test launch code? |
| Retrieved Chunk IDs | `e2a93e55-263c-5ec7-a836-364dc5b26127` |
| Context Chunk IDs | `e2a93e55-263c-5ec7-a836-364dc5b26127` |
| Citation IDs | `C1` |
| Citation Chunk IDs | `e2a93e55-263c-5ec7-a836-364dc5b26127` |
| Prompt Tokens | 139 |
| Completion Tokens | 23 |
| Provider First Token | 1218 ms |
| Client First Token | 2250 ms |
| Provider Total Latency | 1748 ms |
| Client Total Latency | 2786 ms |
| Token Events | 3 |
| Incremental Stream | PASS - first token observed before `done` through `localhost:8080` |
| Result | PASS |

The smoke runner used `ResponseHeadersRead` and parsed each SSE line as it arrived through Nginx.
It verified that the first of 3 token events arrived before `done`, and that every citation chunk
ID was present in the scoped retrieval result before emitting PASS. The run used Google's
OpenAI-compatible endpoint with `gemini-embedding-2` (3072 dimensions) and `gemini-3.5-flash-lite`.
No external secret was logged or committed.

## RAG-E2E-02 Local evidence

| Field | Value |
|---|---|
| Execution Date | 2026-09-27T09:19:40.6944987Z |
| Git Commit | `b34301f2622b4cef9fc9dd5496b4c7893ad29f51` |
| Mode | Local |
| Workspace | `1c89c27a-0a1c-4b16-9dfa-a0a29624d9c9` |
| Embedding Provider | `LOCAL_SENTENCE_TRANSFORMER` |
| Embedding Model | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| Chat Provider | `OLLAMA` |
| Chat Model | `gemma3:1b` |
| Document | `5058b41d-1833-48a5-aaaf-ce7742dbe6a7` |
| Question | What is the RagHub smoke test launch code? |
| Retrieved Chunk IDs | `fdb03010-e82c-51b7-bf51-7208cc69c7a5` |
| Context Chunk IDs | `fdb03010-e82c-51b7-bf51-7208cc69c7a5` |
| Citation IDs | `C1` |
| Citation Chunk IDs | `fdb03010-e82c-51b7-bf51-7208cc69c7a5` |
| Prompt Tokens | 165 |
| Completion Tokens | 40 |
| Provider First Token | 1964 ms |
| Client First Token | 2136 ms |
| Provider Total Latency | 3520 ms |
| Client Total Latency | 3703 ms |
| Token Events | 39 |
| Incremental Stream | PASS - first token observed before `done` through `localhost:8080` |
| Result | PASS |

The smoke runner used `ResponseHeadersRead` and parsed each SSE line as it arrived through Nginx.
It verified that the first of 39 token events arrived before `done`, and that every citation chunk
ID was present in the scoped retrieval result before emitting PASS. The run used the generated
temporary text document and did not use an external LLM API.

## Regression evidence

| Check | Result |
|---|---|
| Ruff | PASS |
| Backend pytest | PASS - 127 passed, 7 skipped integration markers |
| Alembic clean DB upgrade | PASS |
| Alembic clean DB check | PASS - no new upgrade operations |
| Angular tests | PASS - 2 files, 3 tests |
| Angular production build | PASS |
| Docker Compose config | PASS with root `.env` supplied explicitly |

The long-lived local PostgreSQL volume contains two redundant legacy indexes that are not created
by the current migration chain. A fresh database, matching GitHub CI behavior, upgraded and passed
`alembic check`. This local-volume drift is recorded but is not a migration-chain failure.

## External verification command

Executed with `GEMINI_API_KEY` in the ignored root `.env` file:

```powershell
.\scripts\rag-chat-smoke.ps1 -Mode External `
  -ResultPath .\artifacts\rag-external-result.json
```

Result persisted at `artifacts/rag-external-result.json`. No external provider secret was added to the
report or committed to the repository.
