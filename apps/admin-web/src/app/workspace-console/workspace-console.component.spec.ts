import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { of } from "rxjs";
import { vi } from "vitest";

import { RaghubApiService } from "../core/raghub-api.service";
import { WorkspaceConsoleComponent } from "./workspace-console.component";

describe("WorkspaceConsoleComponent", () => {
  it("offers one workspace creation action when no workspace exists", async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            members: () => of([]),
            organizations: () =>
              of([{ id: "org-1", name: "Demo", slug: "demo", role: "ADMIN" }]),
            workspaces: () => of([]),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain(
      "Tạo workspace đầu tiên",
    );
  });

  it("renders the next actions when a workspace is not ready for chat", async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            members: () => of([]),
            organizations: () =>
              of([{ id: "org-1", name: "Demo", slug: "demo", role: "ADMIN" }]),
            workspaces: () =>
              of([
                {
                  id: "workspace-1",
                  name: "Knowledge",
                  slug: "knowledge",
                  organization_id: "org-1",
                },
              ]),
            providers: () => of([]),
            documents: () => of([]),
            chatbots: () => of([]),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain("Thiết lập AI");
    expect(text).toContain("Tải tài liệu");
    expect(text).toContain("Xuất bản chatbot");
  });

  it("uses a safe mapped error and retry for a retryable failed document", async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            members: () => of([]),
            organizations: () =>
              of([{ id: "org-1", name: "Demo", slug: "demo", role: "ADMIN" }]),
            workspaces: () =>
              of([
                {
                  id: "workspace-1",
                  name: "Knowledge",
                  slug: "knowledge",
                  organization_id: "org-1",
                },
              ]),
            providers: () => of([]),
            chatbots: () => of([]),
            documents: () =>
              of([
                {
                  id: "document-1",
                  name: "handbook.pdf",
                  status: "FAILED",
                  stage: "FAILED",
                  created_at: "2026-09-29T00:00:00Z",
                  document_version_id: "version-1",
                  job_id: null,
                  progress: 65,
                  attempts: 1,
                  error_code: "INDEX_UNAVAILABLE",
                  error_message: "password=secret host=private.internal",
                  retryable: true,
                },
              ]),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain("tạm thời không khả dụng");
    expect(text).not.toContain("password=secret");
    expect(text).not.toContain("private.internal");
    expect(text).toContain("Thử lại");
  });

  it("explains that a draft chatbot must be published before chat", async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            members: () => of([]),
            organizations: () =>
              of([{ id: "org-1", name: "Demo", slug: "demo", role: "ADMIN" }]),
            workspaces: () =>
              of([
                {
                  id: "workspace-1",
                  name: "Knowledge",
                  slug: "knowledge",
                  organization_id: "org-1",
                },
              ]),
            providers: () => of([]),
            documents: () => of([]),
            chatbots: () =>
              of([
                {
                  id: "bot-1",
                  workspace_id: "workspace-1",
                  name: "Assistant",
                  system_prompt: "",
                  model: null,
                  retrieval_limit: 5,
                  published: false,
                  created_at: "",
                  updated_at: null,
                },
              ]),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain("Xuất bản chatbot");
    expect(fixture.nativeElement.querySelector("textarea")?.disabled).toBe(
      true,
    );
  });

  it("hides chatbot configuration for workspace admins", async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            members: () => of([]),
            organizations: () =>
              of([
                {
                  id: "org-1",
                  name: "Demo",
                  slug: "demo",
                  role: "WORKSPACE_ADMIN",
                },
              ]),
            workspaces: () =>
              of([
                {
                  id: "workspace-1",
                  name: "Knowledge",
                  slug: "knowledge",
                  organization_id: "org-1",
                },
              ]),
            providers: () => of([]),
            documents: () => of([]),
            chatbots: () => of([]),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const text = element.textContent as string;
    expect(element.querySelector(".setup-panel")).toBeNull();
    const buttons = Array.from(element.querySelectorAll("button")).map(
      (button) => button.textContent?.trim(),
    );
    expect(buttons).not.toContain("Thiết lập");
    expect(element.querySelector(".bot-panel")).not.toBeNull();
    expect(text).toContain("CHATBOT ĐÃ CẤU HÌNH");
    expect(text).toContain("Hỏi tài liệu");
    expect(text).toContain("Tài liệu");
  });

  it("selects a citation by id and falls back to document name", async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: { organizations: () => of([]), workspaces: () => of([]) },
        },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    const component = fixture.componentInstance as any;
    component.documents.set([
      { id: "doc-1", name: "handbook.pdf", status: "READY" },
      { id: "doc-2", name: "policy.pdf", status: "READY" },
    ]);

    component.selectCitation({
      document_id: "doc-2",
      document_name: "handbook.pdf",
    });
    expect(component.selectedDocumentId()).toBe("doc-2");
    component.selectCitation({ document_name: "handbook.pdf" });
    expect(component.selectedDocumentId()).toBe("doc-1");
  });

  it("offers Gemini setup with the configured Flash Lite chat model", async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            members: () => of([]),
            organizations: () =>
              of([{ id: "org-1", name: "Demo", slug: "demo", role: "ADMIN" }]),
            workspaces: () =>
              of([
                {
                  id: "workspace-1",
                  name: "Knowledge",
                  slug: "knowledge",
                  organization_id: "org-1",
                },
              ]),
            providers: () => of([]),
            documents: () => of([]),
            chatbots: () => of([]),
          },
        },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    fixture.detectChanges();
    (fixture.componentInstance as any).setupOpen.set(true);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const model = (
      fixture.nativeElement as HTMLElement
    ).querySelector<HTMLInputElement>('input[name="geminiChatModel"]');
    expect(model?.value).toBe("gemini-3.5-flash-lite");
  });

  it("reuses the existing Gemini providers instead of creating duplicates", async () => {
    const createProvider = vi.fn();
    const embedding = {
      id: "embedding-1",
      provider_type: "GOOGLE_GEMINI",
      capability: "EMBEDDING",
      model: "gemini-embedding-2",
    };
    const chat = {
      id: "chat-1",
      provider_type: "GOOGLE_GEMINI",
      capability: "CHAT",
      model: "gemini-3.5-flash-lite",
    };
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            members: () => of([]),
            organizations: () =>
              of([{ id: "org-1", name: "Demo", slug: "demo", role: "ADMIN" }]),
            workspaces: () =>
              of([
                {
                  id: "workspace-1",
                  name: "Knowledge",
                  slug: "knowledge",
                  organization_id: "org-1",
                },
              ]),
            providers: () => of([embedding, chat]),
            documents: () => of([]),
            chatbots: () => of([]),
            createProvider,
            updateProvider: (id: string) => of({ id }),
            bindWorkspaceProviders: () => of({}),
          },
        },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    (fixture.componentInstance as any).geminiApiKey = "test-key";
    (fixture.componentInstance as any).configureGemini();

    expect(createProvider).not.toHaveBeenCalled();
    fixture.destroy();
  });
});
