# Chatbot Admin UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Expose the existing Sprint 4 RAG-chat backend through a usable Angular admin workflow.

**Architecture:** Extend the existing API service with typed provider/chatbot operations and an incremental SSE reader. Add one standalone ChatbotsComponent with prerequisite states, local/Gemini provider setup, chatbot configuration, and a streaming transcript. Reuse the existing auth interceptor/session organization scope.

**Tech Stack:** Angular 21, TypeScript, RxJS, NG-ZORRO, Vitest/TestBed, existing FastAPI APIs.

**Spec:** docs/superpowers/specs/2026-09-28-chatbot-admin-design.md

## Global Constraints

- Reuse existing backend endpoints; do not add widget, public API-key, or backend functionality.
- Never render or persist provider secrets after submitting a setup form.
- Local defaults are sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (384) and gemma3:4b.
- Render only backend-returned citations.

## Review Focus

- Empty organization/workspace must not trigger scoped requests; Task 2 tests this state.
- Provider secret must leave the UI after submission; Task 2 tests this behavior.
- SSE frames split over chunks must be buffered; Task 1 tests the parser.
- SSE error after streamed tokens preserves displayed text; Task 3 tests this behavior.
- A non-published chatbot cannot submit chat; Task 3 tests this behavior.

---

### Task 1: Chatbot API client and SSE parser

**Files:**
- Modify: apps/admin-web/src/app/core/raghub-api.service.ts
- Create: apps/admin-web/src/app/core/raghub-api.service.spec.ts

**Interfaces:**
- Produces: ProviderConfig, Chatbot, Citation, ChatStreamEvent, SseEventParser, and typed provider/chatbot service methods.
- Consumes: HttpClient and auth/organization values stored by api-auth.interceptor.ts.

- [ ] **Step 1: Write the failing tests**

    it('buffers an incomplete SSE frame', () => {
      const parser = new SseEventParser();
      expect(parser.push('event: token\\ndata: {"text":"Xin ')).toEqual([]);
      expect(parser.push('chào"}\\n\\n')).toEqual([
        { event: 'token', data: { text: 'Xin chào' } },
      ]);
    });

    it('posts a local embedding configuration', () => {
      service.createProvider('org-1', payload).subscribe();
      const request = http.expectOne('/api/v1/organizations/org-1/providers');
      expect(request.request.body).toEqual(payload);
    });

- [ ] **Step 2: Run the test to verify it fails**

    cd apps/admin-web
    npm test -- --runInBand

Expected: FAIL because the parser and provider methods do not exist.

- [ ] **Step 3: Implement the minimal client**

Add typed REST methods for provider list/create/test/bind, chatbot list/create/update, and streamChat. SseEventParser stores a text buffer, splits only at double newlines, parses event/data fields, and returns ChatStreamEvent records. streamChat uses fetch with Authorization and X-Organization-ID session storage headers, TextDecoder streaming, and forwards terminal error events.

- [ ] **Step 4: Verify tests pass**

    cd apps/admin-web
    npm test -- --runInBand

- [ ] **Step 5: Commit**

    git add apps/admin-web/src/app/core/raghub-api.service.ts apps/admin-web/src/app/core/raghub-api.service.spec.ts
    git commit -m "feat(admin): add chatbot API client"

### Task 2: Provider-aware Chatbot page and navigation

**Files:**
- Create: apps/admin-web/src/app/chatbots/chatbots.component.ts
- Create: apps/admin-web/src/app/chatbots/chatbots.component.html
- Create: apps/admin-web/src/app/chatbots/chatbots.component.css
- Create: apps/admin-web/src/app/chatbots/chatbots.component.spec.ts
- Modify: apps/admin-web/src/app/app.routes.ts
- Modify: apps/admin-web/src/app/app.component.html

**Interfaces:**
- Consumes: Task 1 provider types and calls plus existing organizations/workspaces methods.
- Produces: /chatbots route with selected workspace and working provider bindings for Task 3.

- [ ] **Step 1: Write the failing prerequisite tests**

    it('shows the organization prerequisite and skips workspace calls', () => {
      api.organizations = () => of([]);
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain('Tạo tổ chức đầu tiên');
      expect(api.workspaces).not.toHaveBeenCalled();
    });

    it('clears a provider secret after setup succeeds', () => {
      component.geminiSecret = 'do-not-render';
      component.configureGemini();
      expect(component.geminiSecret).toBe('');
      expect(fixture.nativeElement.textContent).not.toContain('do-not-render');
    });

- [ ] **Step 2: Run the test to verify it fails**

    cd apps/admin-web
    npm test -- --runInBand

Expected: FAIL because ChatbotsComponent does not exist.

- [ ] **Step 3: Implement the setup workflow**

Load organizations, persist selected organization with session.organizationId, then load workspaces. Render ordered panels: workspace, AI setup, chatbot settings, and chat test. The local action creates and tests LOCAL_SENTENCE_TRANSFORMER embedding and OLLAMA chat providers, then binds both to the selected workspace. The Gemini action accepts a write-only key and creates GOOGLE_GEMINI embedding/chat providers. While a request is in flight, disable the action. Add the /chatbots route and turn the sidebar Chatbot item into a router link.

- [ ] **Step 4: Verify tests pass**

    cd apps/admin-web
    npm test -- --runInBand

- [ ] **Step 5: Commit**

    git add apps/admin-web/src/app/chatbots apps/admin-web/src/app/app.routes.ts apps/admin-web/src/app/app.component.html
    git commit -m "feat(admin): add chatbot setup workflow"

### Task 3: Chatbot settings, streamed transcript, and citations

**Files:**
- Modify: apps/admin-web/src/app/chatbots/chatbots.component.ts
- Modify: apps/admin-web/src/app/chatbots/chatbots.component.html
- Modify: apps/admin-web/src/app/chatbots/chatbots.component.css
- Modify: apps/admin-web/src/app/chatbots/chatbots.component.spec.ts

**Interfaces:**
- Consumes: Task 1 ChatStreamEvent and chatbot calls; Task 2 selected workspace/provider state.
- Produces: persisted chatbot settings, stream transcript, trusted citation list, and terminal status.

- [ ] **Step 1: Write the failing chat tests**

    it('creates a published chatbot for the selected workspace', () => {
      component.chatbotName = 'Tư vấn tuyển sinh';
      component.createChatbot();
      expect(api.createChatbot).toHaveBeenCalledWith('workspace-1', {
        name: 'Tư vấn tuyển sinh', system_prompt: '', retrieval_limit: 5, published: true,
      });
    });

    it('preserves tokens when the stream reports an error', async () => {
      await component.ask('Học phí bao nhiêu?');
      emit({ event: 'token', data: { text: 'Theo tài liệu, ' } });
      emit({ event: 'error', data: { code: 'PROVIDER_UNAVAILABLE', message: 'Không thể tạo câu trả lời.' } });
      expect(component.answer()).toBe('Theo tài liệu, ');
      expect(component.chatError()).toContain('Không thể tạo câu trả lời.');
    });

- [ ] **Step 2: Run the test to verify it fails**

    cd apps/admin-web
    npm test -- --runInBand

Expected: FAIL because chatbot form and stream state are absent.

- [ ] **Step 3: Implement chatbot settings and chat test**

Create/update name, system prompt, retrieval limit (1–10), and published state. Load chatbot records after workspace selection. Only enable question submission for a selected published chatbot and configured workspace. On conversation save conversation_id; on token append answer; on citations replace citations; on error show safe terminal error without clearing answer; on done mark complete. Render citation document name, optional page, and excerpt. Disable the send button while streaming.

- [ ] **Step 4: Verify UI and production build**

    cd apps/admin-web
    npm test -- --runInBand
    npm run build

Expected: PASS tests and build.

- [ ] **Step 5: Commit**

    git add apps/admin-web/src/app/chatbots
    git commit -m "feat(admin): add streamed chatbot panel"

### Task 4: Local end-to-end verification

**Files:**
- Modify: README.md

**Interfaces:**
- Consumes: completed /chatbots UI and local Docker stack.
- Produces: a concise operating path from document READY to grounded chat.

- [ ] **Step 1: Add the manual verification checklist**

    1. Open /chatbots and select the workspace.
    2. Confirm local provider readiness.
    3. Confirm a document is READY.
    4. Create and publish a chatbot.
    5. Ask a question present in the document.
    6. Confirm streamed text and source citations.

- [ ] **Step 2: Run the end-to-end check**

    docker compose --env-file .env -f infrastructure/docker-compose.yml --profile local-ai up --build -d --wait

Open http://localhost:8080/chatbots. Expected: local setup, chatbot creation, and streamed answer do not require Swagger.

- [ ] **Step 3: Run final checks**

    cd apps/admin-web
    npm test -- --runInBand
    npm run build

- [ ] **Step 4: Commit**

    git add README.md
    git commit -m "docs: add admin chatbot workflow"

## Self-review

- Provider setup, chatbot CRUD, SSE, citations, error states, and documentation map to Tasks 1–4.
- The five review-focus risks are each exercised by a named test.
- Task 1 defines every service type consumed later.

