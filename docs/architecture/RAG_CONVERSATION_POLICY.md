# RAG conversation policy

The same `StreamRagChatUseCase` serves authenticated Playground and public delivery.
Authorization, public key resolution, origin validation and Redis admission happen
outside the engine before a command is built.

## Turn persistence

1. Resolve and validate the chatbot and conversation owner.
2. Load previous history, excluding failed assistant messages.
3. Stage the submitted user message and explicitly commit it before retrieval or AI.
4. Decide whether the turn can be answered now, needs clarification, or must be safely redirected.
5. For normal answer turns, generate the answer. The core appends the current question to previous history.
6. On normal success, stage the assistant, trusted citations and usage, then commit together.
7. On clarification, stage the assistant clarification message and zero-token usage, then commit together.
8. On a provider/retrieval error, commit a failed assistant with its partial content
   and error code, then emit the typed failure event. Do not record completed usage
   or emit `done` for that turn. Do not retry after a token has been emitted.

Adapters flush staged writes; the application use case owns commit decisions.
Provider resolution failures and provider timeouts use the same failure policy.
Unexpected errors during provider streaming use a generic `CHAT_RUNTIME_FAILED`
message rather than exposing vendor response text.

## SSE event order

Normal answer turns keep the existing order:

1. `conversation`
2. `citations`
3. zero or more `token`
4. `usage`
5. `done`

Empty-context fallback remains a normal completed turn with empty citations, a fallback token,
zero-token usage and `done`.

Clarification turns use a separate completed-turn order:

1. `conversation`
2. `clarification`
3. `usage` with `prompt_tokens = 0`, `completion_tokens = 0`, `total_tokens = 0`, `source = "none"`
4. `done`

Clarification turns do not emit `citations` or `token` because no retrieval result or model token is
being streamed. Emitting zero usage keeps older clients from handling a missing usage branch once
Phase 3 wires the runtime behavior.

Failure turns emit `conversation` when the user message was durably stored, then `error`; they do not
emit `usage` or `done`.

## Clarification contract

`ClarificationRequested` is a domain event serialized by HTTP delivery as `event: clarification`.
Its payload is intentionally small and deterministic:

- `message`: the Vietnamese clarification question shown to the user.
- `missing_slots`: normalized slot names the engine still needs.
- `suggestions`: optional short suggested replies; clients may ignore them.
- `reason`: stable machine-readable reason such as `missing_required_slot`.

Clients that do not know the `clarification` event should ignore it safely according to the SSE
parser contract. The public widget currently ignores unknown event names, so Phase 1 is backward
compatible; Phase 5 will render clarification text explicitly.

## Existing schema

This refactor does not add a message status column in Phase 1. A successful assistant retains
its existing usage metadata and is implicitly completed. A clarification assistant is also a
completed assistant message with zero-token usage and no citation rows. A failed assistant uses
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
