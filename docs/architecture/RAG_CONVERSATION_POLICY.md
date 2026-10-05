# RAG conversation policy

The same `StreamRagChatUseCase` serves authenticated Playground and public delivery.
Authorization, public key resolution, origin validation and Redis admission happen
outside the engine before a command is built.

## Turn persistence

1. Resolve and validate the chatbot and conversation owner.
2. Load previous history, excluding failed assistant messages.
3. Stage the submitted user message and explicitly commit it before retrieval or AI.
4. Generate the answer. The core appends the current question to previous history.
5. On success, stage the assistant, trusted citations and usage, then commit together.
6. On a provider/retrieval error, commit a failed assistant with its partial content
   and error code, then emit the typed failure event. Do not record completed usage
   or emit `done` for that turn. Do not retry after a token has been emitted.

Adapters flush staged writes; the application use case owns commit decisions.
Provider resolution failures and provider timeouts use the same failure policy.
Unexpected errors during provider streaming use a generic `CHAT_RUNTIME_FAILED`
message rather than exposing vendor response text.

## Existing schema

This refactor does not add a message status column. A successful assistant retains
its existing usage metadata and is implicitly completed. A failed assistant uses
`messages.usage_json = {"status": "FAILED", "error_code": "..."}`. Its partial text
is retained for diagnostics but excluded from subsequent prompts. The user question
remains in history. Failure records have no usage event or trusted citation rows.

Cancellation/disconnection leaves the committed user message and does not write a
completed assistant or usage event. The public delivery deadline behaves the same
way when it cancels an in-flight turn. A provider's own timeout is a recorded failed
turn. Public delivery closes the iterator and releases its concurrency lease even
when streaming, cancellation or serialization fails.

No SDK, HTTP status or SSE frame appears in the conversation port or core policy.
Core errors contain code/message/details; HTTP delivery chooses status codes.
