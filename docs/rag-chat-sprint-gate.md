# RAG chat Sprint 5 gate report

## Gate status

| Gate | Result |
|---|---|
| RAG-E2E-01 External | NOT RUN — external provider credentials were not available |
| RAG-E2E-02 Local | PASS |
| Sprint 5 | BLOCKED until RAG-E2E-01 passes |

## RAG-E2E-02 Local evidence

| Field | Value |
|---|---|
| Execution Date | 2026-09-27T08:32:11.2095547Z |
| Git Commit | `315872dcfa58754b68abf63a4888bce703960297` |
| Mode | Local |
| Workspace | `fbbc1a49-c1d4-4486-884a-f70e7582d070` |
| Embedding Provider | `LOCAL_SENTENCE_TRANSFORMER` |
| Embedding Model | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| Chat Provider | `OLLAMA` |
| Chat Model | `gemma3:1b` |
| Document | `4d67e24f-fbb8-4681-9d6a-92852b823b10` |
| Question | What is the RagHub smoke test launch code? |
| Retrieved Chunk IDs | `64725c87-77c7-5eff-bffd-c237d7066cec` |
| Context Chunk IDs | `64725c87-77c7-5eff-bffd-c237d7066cec` |
| Citation IDs | `C1` |
| Citation Chunk IDs | `64725c87-77c7-5eff-bffd-c237d7066cec` |
| Prompt Tokens | 165 |
| Completion Tokens | 48 |
| First Token | 1869 ms |
| Total Latency | 3613 ms |
| Result | PASS |

The smoke runner verified that every citation chunk ID was present in the scoped retrieval result
before emitting PASS. The run used the generated temporary text document and did not use an
external LLM API.

## Required External follow-up

Configure the `RAGHUB_EXTERNAL_*` environment variables described in
`docs/rag-chat-integration.md`, then run:

```powershell
.\scripts\rag-chat-smoke.ps1 -Mode External `
  -ResultPath .\artifacts\rag-external-result.json
```

Update this report only after the result is PASS. No external provider secret may be added to the
report or committed to the repository.
