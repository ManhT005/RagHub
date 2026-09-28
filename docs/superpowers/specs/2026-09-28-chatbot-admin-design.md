# Chatbot Admin UI design

## Purpose

Expose the existing Sprint 4 RAG-chat backend in the Angular admin application. An organization
member should be able to select a workspace, configure local or external providers, create and
publish a chatbot, and ask a grounded question without Swagger.

## Scope

The new `/chatbots` page is the single workflow surface. It reuses existing provider, workspace,
chatbot, and SSE endpoints; it does not add public widget functionality, API keys, rate limits,
or new backend APIs.

## User flow

1. Select an organization and workspace.
2. If the workspace has no configured providers, choose local Ollama or Gemini and save the
   provider bindings. Local defaults are Sentence Transformers embedding and `gemma3:4b` chat.
3. Create a chatbot with name, system prompt, retrieval limit, and published state.
4. Select a published chatbot and ask a question.
5. Display streaming text, terminal status, and trusted citations.

## UI structure

The page uses a left workflow rail and a focused main panel:

```text
Workspace selector | Provider readiness | Chatbot settings | Chat test
```

At every incomplete state the page provides one primary action and explains the prerequisite:
create a workspace, configure providers, create a chatbot, or upload a READY document. Slugs,
provider IDs, and SSE internals stay out of the default user experience.

## Frontend components

- `ChatbotsComponent`: owns organization/workspace selection and workflow state.
- Provider setup form: supports local defaults and Gemini secret input; calls provider create,
  test, and workspace binding endpoints.
- Chatbot form: create, edit, publish, and choose chatbot records.
- Chat test panel: reads the SSE response incrementally, keeps its active conversation ID, and
  renders citations after the answer.
- `RaghubApiService`: gains typed provider/chatbot methods and a streaming chat helper.

## Error handling

Errors name the blocked prerequisite. A failed provider test preserves form data. SSE terminal
errors appear in the chat panel without discarding the earlier response. The UI never shows a
provider secret after submission.

## Verification

- Angular unit tests cover prerequisite states, provider-binding payloads, chatbot creation, and
  SSE event parsing.
- Production Angular build passes.
- Manual flow: local provider setup -> document READY -> publish chatbot -> streamed answer with
  citation.
