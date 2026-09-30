# Workspace Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace separate document and chatbot screens with one responsive Workspace Console that guides the RAG vertical slice.

**Architecture:** A new standalone `WorkspaceConsoleComponent` owns the organization/workspace context and composes document ingestion, readiness, setup and chat. It reuses the existing `RaghubApiService`; the legacy document/chatbot routes redirect to the console.

**Tech Stack:** Angular 21 standalone components, Signals, RxJS, Angular Forms, Vitest, NG-ZORRO and CSS custom properties.

**Spec:** `docs/superpowers/specs/2026-09-29-workspace-console-design.md`

## Global Constraints

- Change Angular Admin only; do not change backend contracts.
- Keep `design-system-dark` and the existing navy/cyan/indigo token system.
- Never put provider secrets in browser storage or rendered error messages.
- Use existing scoped API calls and the current organization session header.
- Render a text label with every readiness/error state.
- Use a 40/60 document/chat grid above 960px and a single column below it.

## Review Focus

- No workspace must show exactly one clear creation action (Task 1 test).
- A failed document must show a safe mapped error and retry only when retryable (Task 3 test).
- A draft bot must describe why chat is locked (Task 4 test).
- Citation selection must use document id, then name fallback without throwing (Task 4 test).
- Switching workspace must clear the old transcript and selected document before scoped data loads (Task 2 test).

---

## File Structure

- Create `apps/admin-web/src/app/workspace-console/workspace-console.component.ts`: workspace state, document commands, provider/chatbot setup and streaming.
- Create `apps/admin-web/src/app/workspace-console/workspace-console.component.html`: context bar, checklist, document panel, assistant panel and setup panel.
- Create `apps/admin-web/src/app/workspace-console/workspace-console.component.css`: dark responsive console layout.
- Create `apps/admin-web/src/app/workspace-console/workspace-console.component.spec.ts`: component integration tests with an API fake.
- Modify `apps/admin-web/src/app/app.routes.ts`, `app.component.html`, dashboard and organization settings presentation.

### Task 1: Add Console route and empty workspace state

**Files:**
- Create: `apps/admin-web/src/app/workspace-console/workspace-console.component.ts`
- Create: `apps/admin-web/src/app/workspace-console/workspace-console.component.html`
- Create: `apps/admin-web/src/app/workspace-console/workspace-console.component.css`
- Create: `apps/admin-web/src/app/workspace-console/workspace-console.component.spec.ts`
- Modify: `apps/admin-web/src/app/app.routes.ts`
- Modify: `apps/admin-web/src/app/app.component.html`

**Interfaces:**
- Consumes: `organizations(): Observable<Organization[]>`, `workspaces(): Observable<Workspace[]>`.
- Produces: `WorkspaceConsoleComponent` at `/workspaces`; `/documents` and `/chatbots` redirect there.

- [ ] **Step 1: Write the failing test**

~~~ts
it('offers one workspace creation action when no workspace exists', async () => {
  await TestBed.configureTestingModule({
    imports: [WorkspaceConsoleComponent],
    providers: [{ provide: RaghubApiService, useValue: {
      organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
      workspaces: () => of([]),
    } }],
  }).compileComponents();
  const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
  fixture.detectChanges();
  expect(fixture.nativeElement.textContent).toContain('Tạo workspace đầu tiên');
});
~~~

- [ ] **Step 2: Verify red**

Run: `npm.cmd test -- --watch=false --include src/app/workspace-console/workspace-console.component.spec.ts`

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement the context shell**

~~~ts
export class WorkspaceConsoleComponent {
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly workspaces = signal<Workspace[]>([]);
  protected selectedOrganization = session.organizationId ?? '';
  protected selectedWorkspace = '';
}
~~~

Load organizations, then workspaces. Render an accessible context bar. When no workspace exists, render an explanation and only the `routerLink="/settings"` action `Tạo workspace đầu tiên`. Add routes for `/workspaces` and `/settings`; redirect both legacy routes to `/workspaces`.

- [ ] **Step 4: Verify green**

Run: `npm.cmd test -- --watch=false --include src/app/workspace-console/workspace-console.component.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

~~~powershell
git add apps/admin-web/src/app/workspace-console apps/admin-web/src/app/app.routes.ts apps/admin-web/src/app/app.component.html
git commit -m "feat: add workspace console shell"
~~~

### Task 2: Load scoped resources and readiness

**Files:**
- Modify: `apps/admin-web/src/app/workspace-console/workspace-console.component.ts`
- Modify: `apps/admin-web/src/app/workspace-console/workspace-console.component.html`
- Modify: `apps/admin-web/src/app/workspace-console/workspace-console.component.spec.ts`

**Interfaces:**
- Consumes: `providers(organizationId)`, `documents(workspaceId)`, `chatbots(workspaceId)`.
- Produces: `changeOrganization()`, `changeWorkspace()`, `clearWorkspaceState()`, readiness computed Signals.

- [ ] **Step 1: Write failing tests**

~~~ts
it('clears old chat and document selection before loading another workspace', () => {
  const component = fixture.componentInstance as any;
  component.messages.set([{ role: 'user', content: 'old question' }]);
  component.selectedDocumentId.set('doc-a');
  component.selectedWorkspace = 'workspace-b';
  component.changeWorkspace();
  expect(component.messages()).toEqual([]);
  expect(component.selectedDocumentId()).toBe('');
});

it('renders next actions for missing provider, ready document and publish state', () => {
  expect(fixture.nativeElement.textContent).toContain('Thiết lập AI');
  expect(fixture.nativeElement.textContent).toContain('Tải tài liệu');
  expect(fixture.nativeElement.textContent).toContain('Xuất bản chatbot');
});
~~~

- [ ] **Step 2: Verify red**

Run: `npm.cmd test -- --watch=false --include src/app/workspace-console/workspace-console.component.spec.ts`

Expected: FAIL because resource state and readiness do not exist.

- [ ] **Step 3: Implement scoped state**

Add Signals for providers, documents, bots, selected bot, selected document id, transcript, error and notice. Clear them before every workspace-scoped load. Use:

~~~ts
protected readonly hasReadyDocument = computed(() =>
  this.documents().some((item) => item.status === 'READY'));
protected readonly hasChatProvider = computed(() =>
  this.providers().some((item) => item.capability === 'CHAT' && item.enabled));
protected readonly hasPublishedBot = computed(() => Boolean(this.selectedBot()?.published));
~~~

Render explicit `Cần thiết lập` or `Sẵn sàng` labels and buttons that open setup or focus upload. Provider readiness means an enabled available chat provider; do not claim persistent binding because the existing API has no binding read endpoint.

- [ ] **Step 4: Verify green**

Run: `npm.cmd test -- --watch=false --include src/app/workspace-console/workspace-console.component.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

~~~powershell
git add apps/admin-web/src/app/workspace-console
git commit -m "feat: show workspace readiness checklist"
~~~

### Task 3: Put ingestion controls in the document panel

**Files:**
- Modify: `apps/admin-web/src/app/workspace-console/workspace-console.component.ts`
- Modify: `apps/admin-web/src/app/workspace-console/workspace-console.component.html`
- Modify: `apps/admin-web/src/app/workspace-console/workspace-console.component.css`
- Modify: `apps/admin-web/src/app/workspace-console/workspace-console.component.spec.ts`

**Interfaces:**
- Consumes: `upload`, `retryDocument`, `reindexDocument`, `deleteDocument`, and `ingestionErrorMessage`.
- Produces: `upload()`, `retry(document)`, `reindex(document)`, `remove(document)`, `statusLabel(status)`, `selectDocument(id)`.

- [ ] **Step 1: Write the failing safe-error test**

~~~ts
it('uses a safe mapped error and retry only for a retryable failed document', () => {
  fixture.detectChanges();
  const text = fixture.nativeElement.textContent as string;
  expect(text).toContain('tạm thời không khả dụng');
  expect(text).not.toContain('password=secret');
  expect(text).not.toContain('private.internal');
  expect(text).toContain('Thử lại');
});
~~~

The fake document must contain `error_code: 'INDEX_UNAVAILABLE'`, `retryable: true`, and `error_message: 'password=secret host=private.internal'`.

- [ ] **Step 2: Verify red**

Run: `npm.cmd test -- --watch=false --include src/app/workspace-console/workspace-console.component.spec.ts`

Expected: FAIL because the document panel is absent.

- [ ] **Step 3: Implement document ingestion**

Port the current DocumentsComponent behavior: labelled upload control, document list, stage/progress, retry/re-index/delete, and 3-second polling only for nonterminal documents. Use `ingestionErrorMessage(error_code)` only; never render backend `error_message`. Add the selected row style for `document.id === selectedDocumentId()`.

- [ ] **Step 4: Verify green**

Run: `npm.cmd test -- --watch=false --include src/app/workspace-console/workspace-console.component.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

~~~powershell
git add apps/admin-web/src/app/workspace-console
git commit -m "feat: manage documents inside workspace console"
~~~

### Task 4: Put setup, assistant and citation focus in the right panel

**Files:**
- Modify: `apps/admin-web/src/app/workspace-console/workspace-console.component.ts`
- Modify: `apps/admin-web/src/app/workspace-console/workspace-console.component.html`
- Modify: `apps/admin-web/src/app/workspace-console/workspace-console.component.css`
- Modify: `apps/admin-web/src/app/workspace-console/workspace-console.component.spec.ts`

**Interfaces:**
- Consumes: existing provider, chatbot and `streamChat` API methods.
- Produces: `openSetup(section)`, `configureLocal()`, `configureGemini()`, `bindProviders()`, `saveBot()`, `togglePublish()`, `send()`, `selectCitation(citation)`.

- [ ] **Step 1: Write failing guard and citation tests**

~~~ts
it('explains that a draft chatbot must be published before chat', () => {
  fixture.detectChanges();
  expect(fixture.nativeElement.textContent).toContain('Xuất bản chatbot');
  expect(fixture.nativeElement.querySelector('textarea')?.disabled).toBe(true);
});

it('selects a citation by id and falls back to document name', () => {
  const component = fixture.componentInstance as any;
  component.documents.set([{ id: 'doc-1', name: 'handbook.pdf', status: 'READY' }]);
  component.selectCitation({ document_id: 'doc-1', document_name: 'other.pdf' });
  expect(component.selectedDocumentId()).toBe('doc-1');
  component.selectCitation({ document_name: 'handbook.pdf' });
  expect(component.selectedDocumentId()).toBe('doc-1');
});
~~~

- [ ] **Step 2: Verify red**

Run: `npm.cmd test -- --watch=false --include src/app/workspace-console/workspace-console.component.spec.ts`

Expected: FAIL because setup, guard and citation selection are absent.

- [ ] **Step 3: Implement setup and assistant**

Port the current provider/chatbot behavior unchanged: local embedding `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, Ollama `gemma3:4b`, Gemini chat `gemini-3.5-flash-lite`, Gemini embedding `gemini-embedding-2`, base URL `https://generativelanguage.googleapis.com/v1beta/openai`, dimension `3072`.

Use `setupSection = signal<'provider' | 'chatbot' | null>(null)` for the compact settings panel. Port streaming unchanged. Extend local citation data with `document_id?: string`; select id first then matching name; no-op on no match. Citation source controls are buttons with name/page text.

- [ ] **Step 4: Verify green**

Run: `npm.cmd test -- --watch=false --include src/app/workspace-console/workspace-console.component.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

~~~powershell
git add apps/admin-web/src/app/workspace-console
git commit -m "feat: add workspace assistant and setup panels"
~~~

### Task 5: Make overview and organization management supporting screens

**Files:**
- Modify: `apps/admin-web/src/app/dashboard/dashboard.component.ts`
- Modify: `apps/admin-web/src/app/dashboard/dashboard.component.html`
- Modify: `apps/admin-web/src/app/dashboard/dashboard.component.css`
- Modify: `apps/admin-web/src/app/workspaces/workspaces.component.html`
- Modify: `apps/admin-web/src/app/workspaces/workspaces.component.css`
- Modify: `apps/admin-web/src/app/app.component.html`
- Modify: `apps/admin-web/src/app/app.spec.ts`

**Interfaces:**
- Consumes: existing workspace API and organization/member CRUD.
- Produces: concise overview linking to the console and a settings page visibly labelled `Cài đặt tổ chức`.

- [ ] **Step 1: Write failing navigation test**

~~~ts
it('links navigation to Workspace Console and organization settings', () => {
  const text = fixture.nativeElement.textContent as string;
  expect(text).toContain('Không gian làm việc');
  expect(text).toContain('Cài đặt tổ chức');
  expect(fixture.nativeElement.querySelector('a[href="/workspaces"]')).not.toBeNull();
});
~~~

- [ ] **Step 2: Verify red**

Run: `npm.cmd test -- --watch=false --include src/app/app.spec.ts`

Expected: FAIL because documents and chatbot are still sidebar entries.

- [ ] **Step 3: Implement supporting screens**

Replace dashboard infrastructure marketing with a small workspace-oriented overview and primary `Mở Workspace Console` action. Rename the visible workspace CRUD page to `Cài đặt tổ chức`; keep all existing forms. Remove separate Tài liệu/Chatbot sidebar entries.

- [ ] **Step 4: Verify green**

Run: `npm.cmd test -- --watch=false --include src/app/app.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

~~~powershell
git add apps/admin-web/src/app/dashboard apps/admin-web/src/app/workspaces apps/admin-web/src/app/app.component.html apps/admin-web/src/app/app.spec.ts
git commit -m "feat: align navigation with workspace console"
~~~

### Task 6: Verify the full admin web

**Files:**
- Modify: `apps/admin-web/src/app/workspace-console/workspace-console.component.spec.ts` only if a test correction is necessary.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: a test-passing production build.

- [ ] **Step 1: Run all tests**

Run: `npm.cmd test -- --watch=false`

Expected: PASS with no failed test files.

- [ ] **Step 2: Build**

Run: `npm.cmd run build`

Expected: exit 0 and `dist/admin-web` output.

- [ ] **Step 3: Inspect final diff**

Run: `git diff --check; git status --short; git log --oneline -6`

Expected: no whitespace errors and only intended changes.

- [ ] **Step 4: Commit test-only follow-up if one was required**

~~~powershell
git add apps/admin-web/src/app/workspace-console/workspace-console.component.spec.ts
git commit -m "test: cover workspace console workflow"
~~~

Create this commit only if a test-only correction was needed; never create an empty commit.

