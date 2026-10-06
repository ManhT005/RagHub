import { By } from "@angular/platform-browser";
import { ChatbotSettingsComponent } from "./chatbot-settings.component";
import { ComponentFixture, TestBed } from "@angular/core/testing";
import { provideNoopAnimations } from "@angular/platform-browser/animations";
import { ActivatedRoute, convertToParamMap, provideRouter } from "@angular/router";
import { of, throwError } from "rxjs";
import { vi } from "vitest";

import { RaghubApiService } from "../core/raghub-api.service";
import { ChatbotsComponent } from "./chatbots.component";

const embeddingProvider = {
  id: "embedding-1",
  organization_id: "org-1",
  name: "Embedding Gemini",
  provider_type: "GOOGLE_GEMINI" as const,
  capability: "EMBEDDING" as const,
  base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
  model: "gemini-embedding-2",
  dimension: 3072,
  config_json: {},
  enabled: true,
  has_secret: true,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: null,
};

const chatProvider = {
  ...embeddingProvider,
  id: "chat-1",
  name: "Chat Gemini",
  capability: "CHAT" as const,
  model: "gemini-3.5-flash-lite",
  dimension: null,
};

const savedBot = {
  id: "bot-1",
  workspace_id: "workspace-1",
  name: "Trợ lý tài liệu",
  system_prompt: "Chỉ trả lời từ tài liệu.",
  model: null,
  retrieval_limit: 5,
  published: true,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: null,
  allowed_origins: [],
  embed_primary_color: "#1463ff",
  embed_title: "RagHub Assistant",
  embed_greeting: "Xin chào!",
};

const readyDocument = {
  id: "document-1",
  name: "huong-dan.pdf",
  status: "READY",
  created_at: "2026-10-01T01:00:00Z",
  document_version_id: "version-1",
  job_id: "job-1",
  stage: "READY",
  progress: 100,
  attempts: 1,
  error_code: null,
  error_message: null,
  retryable: false,
};

describe("ChatbotsComponent two-step flow", () => {
  async function setup(
    overrides: Record<string, unknown> = {},
    role: "ADMIN" | "WORKSPACE_ADMIN" = "ADMIN",
    requestedWorkspaceId = "",
  ): Promise<{
    fixture: ComponentFixture<ChatbotsComponent>;
    api: Record<string, ReturnType<typeof vi.fn>>;
  }> {
    const api = {
      organizations: vi.fn(() =>
        of([{ id: "org-1", name: "Demo", slug: "demo", role }]),
      ),
      workspaces: vi.fn(() =>
        of([
          {
            id: "workspace-1",
            name: "Knowledge",
            slug: "knowledge",
            organization_id: "org-1",
          },
        ]),
      ),
      providers: vi.fn(() => of([embeddingProvider, chatProvider])),
      chatbots: vi.fn(() => of([])),
      testProvider: vi.fn(() => of({ status: "OK" })),
      bindWorkspaceProviders: vi.fn(() => of({})),
      createChatbot: vi.fn(() => of(savedBot)),
      updateChatbot: vi.fn(() => of(savedBot)),
      updateProvider: vi.fn((id: string) =>
        of(id === embeddingProvider.id ? embeddingProvider : chatProvider),
      ),
      createProvider: vi.fn(),
      publishEmbed: vi.fn(() => of({ code: "<script>embed</script>" })),
      embedCode: vi.fn(() => of({ code: "<script>existing</script>" })),
      rotateEmbedKey: vi.fn(() => of({ code: "<script>rotated</script>" })),
      documents: vi.fn(() => of([])),
      upload: vi.fn(() => of({})),
      retryDocument: vi.fn(() => of({})),
      reindexDocument: vi.fn(() => of({})),
      deleteDocument: vi.fn(() => of({})),
      streamChat: vi.fn(() => Promise.resolve()),
      ...overrides,
    } as Record<string, ReturnType<typeof vi.fn>>;

    await TestBed.configureTestingModule({
      imports: [ChatbotsComponent],
      providers: [
        provideRouter([]),
        provideNoopAnimations(),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParamMap: convertToParamMap({
                workspaceId: requestedWorkspaceId,
              }),
            },
          },
        },
        { provide: RaghubApiService, useValue: api },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(ChatbotsComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, api };
  }

  function openCreate(fixture: ComponentFixture<ChatbotsComponent>): any {
    const component = fixture.componentInstance as any;
    component.openCreateChatbot();
    fixture.detectChanges();
    return component;
  }

  it("opens on a paginated chatbot table and starts creation from the add button", async () => {
    const { fixture } = await setup({ chatbots: vi.fn(() => of([savedBot])) });
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector(".chatbot-list-view nz-table")).not.toBeNull();
    expect(element.textContent).toContain("Trợ lý tài liệu");
    expect(element.querySelector(".create-step")).toBeNull();

    const addButton = element.querySelector(
      ".add-chatbot-button",
    ) as HTMLButtonElement;
    addButton.click();
    fixture.detectChanges();

    expect(element.querySelector(".create-step")).not.toBeNull();
    expect(element.textContent).not.toContain("Chatbot hiện tại");
  });

  it("loads the chatbot list for the workspace selected in the filter", async () => {
    const secondBot = {
      ...savedBot,
      id: "bot-2",
      workspace_id: "workspace-2",
      name: "Trợ lý tuyển sinh",
    };
    const { fixture } = await setup({
      workspaces: vi.fn(() =>
        of([
          {
            id: "workspace-1",
            name: "Knowledge",
            slug: "knowledge",
            organization_id: "org-1",
          },
          {
            id: "workspace-2",
            name: "Tuyển sinh",
            slug: "tuyen-sinh",
            organization_id: "org-1",
          },
        ]),
      ),
      chatbots: vi.fn((workspaceId: string) =>
        of(workspaceId === "workspace-2" ? [secondBot] : [savedBot]),
      ),
    });
    const component = fixture.componentInstance as any;

    component.selectWorkspace("workspace-2");
    fixture.detectChanges();

    expect(component.selectedWorkspace).toBe("workspace-2");
    expect(component.bots().map((bot: typeof savedBot) => bot.name)).toEqual([
      "Trợ lý tuyển sinh",
    ]);
    expect(fixture.nativeElement.textContent).toContain("Trợ lý tuyển sinh");
  });

  it("starts with the workspace requested by the workspace list", async () => {
    const chatbots = vi.fn(() => of([]));
    const { fixture } = await setup(
      {
        workspaces: vi.fn(() =>
          of([
            {
              id: "workspace-1",
              name: "Một",
              slug: "mot",
              organization_id: "org-1",
            },
            {
              id: "workspace-2",
              name: "Hai",
              slug: "hai",
              organization_id: "org-1",
            },
          ]),
        ),
        chatbots,
      },
      "ADMIN",
      "workspace-2",
    );
    const component = fixture.componentInstance as any;

    expect(component.selectedWorkspace).toBe("workspace-2");
    expect(chatbots).toHaveBeenCalledWith("workspace-2");
  });

  it("opens the workspace filter and renders every available workspace", async () => {
    const { fixture } = await setup({
      workspaces: vi.fn(() =>
        of([
          {
            id: "workspace-1",
            name: "HAUI",
            slug: "haui",
            organization_id: "org-1",
          },
          {
            id: "workspace-2",
            name: "Tuyển sinh",
            slug: "tuyen-sinh",
            organization_id: "org-1",
          },
        ]),
      ),
    });
    const select = fixture.nativeElement.querySelector(
      'nz-select[aria-labelledby="workspace-filter-label"] .ant-select-selector',
    ) as HTMLElement;

    expect(select.closest("nz-select")?.className).not.toContain(
      "ant-select-disabled",
    );

    select.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    select.click();
    fixture.detectChanges();
    await fixture.whenStable();

    const component = fixture.componentInstance as any;
    expect(component.workspaceFilterOpen()).toBe(true);
    expect(component.workspaces().map((workspace: any) => workspace.name)).toEqual([
      "HAUI",
      "Tuyển sinh",
    ]);
  });

  it("shows LLM and embedding provider controls in the create form", async () => {
    const { fixture } = await setup();
    openCreate(fixture);
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector(".create-step")).not.toBeNull();
    expect(element.textContent).toContain("Model LLM");
    expect(element.textContent).toContain("Model Embedding");
    expect(element.textContent).toContain("API key");
    expect(element.querySelectorAll(".create-chatbot-cta")).toHaveLength(1);
    expect(element.querySelector(".create-step .ant-input")).not.toBeNull();
    expect(element.querySelector(".create-chatbot-cta.ant-btn-primary")).not.toBeNull();
  });

  it("opens embed settings as a separate action", async () => {
    const { fixture, api } = await setup({
      chatbots: vi.fn(() => of([savedBot])),
    });
    const component = fixture.componentInstance as any;

    component.editChatbot(savedBot);
    fixture.detectChanges();

    expect(
      fixture.nativeElement.querySelector(".embed-settings"),
    ).toBeNull();
    expect(fixture.nativeElement.querySelector(".embed-view")).toBeNull();

    component.openEmbed(savedBot);
    fixture.detectChanges();

    const embedPanel = fixture.nativeElement.querySelector(
      ".embed-view",
    ) as HTMLElement;
    expect(embedPanel).not.toBeNull();
    expect(embedPanel.textContent).toContain("Nhúng chatbot");
    const settings = fixture.debugElement.query(By.directive(ChatbotSettingsComponent)).componentInstance as ChatbotSettingsComponent;
    expect(settings.title).toBe("RagHub Assistant");
    expect(api["embedCode"]).toHaveBeenCalledWith(savedBot.id);
    expect(settings.code()).toBe("<script>existing</script>");
  });

  it("publishes embed settings and exposes the returned code", async () => {
    const { fixture, api } = await setup({
      chatbots: vi.fn(() => of([savedBot])),
    });
    const component = fixture.componentInstance as any;
    component.openEmbed(savedBot);
    fixture.detectChanges();
    const settings = fixture.debugElement.query(By.directive(ChatbotSettingsComponent)).componentInstance as ChatbotSettingsComponent;
    settings.origins = "https://one.example\nhttps://two.example";
    settings.primaryColor = "#123456";
    settings.title = "Trợ lý tuyển sinh";
    settings.greeting = "Xin chào";

    settings.publish();
    fixture.detectChanges();

    expect(api["publishEmbed"]).toHaveBeenCalledWith(savedBot.id, {
      allowed_origins: ["https://one.example", "https://two.example"],
      primary_color: "#123456",
      title: "Trợ lý tuyển sinh",
      greeting: "Xin chào",
    });
    expect(settings.code()).toBe("<script>embed</script>");
    expect(component.selectedBot()?.published).toBe(true);
  });

  it("publishes a chatbot from the list and updates its visible status", async () => {
    const draftBot = { ...savedBot, published: false };
    const { fixture } = await setup({
      chatbots: vi.fn(() => of([draftBot])),
      updateChatbot: vi.fn(() => of(savedBot)),
    });
    const component = fixture.componentInstance as any;

    component.toggleBotPublish(draftBot);
    fixture.detectChanges();

    expect(component.bots()[0].published).toBe(true);
    expect(component.publishingBotId()).toBe("");
    expect(fixture.nativeElement.textContent).toContain("Đã xuất bản");
  });

  it("keeps form values on step one when AI validation fails", async () => {
    const { fixture } = await setup({
      testProvider: vi.fn(() => throwError(() => new Error("invalid key"))),
    });
    const component = openCreate(fixture);
    component.botName = "Trợ lý tuyển sinh";
    component.createChatbotAndContinue();
    fixture.detectChanges();

    expect(component.currentStep()).toBe(1);
    expect(component.botName).toBe("Trợ lý tuyển sinh");
    expect(component.error()).toContain("Google Gemini");
  });

  it("validates AI, publishes the chatbot and opens the document step", async () => {
    const { fixture } = await setup({
      documents: vi.fn(() => of([readyDocument])),
    });
    const component = openCreate(fixture);

    component.createChatbotAndContinue();
    fixture.detectChanges();

    expect(component.currentStep()).toBe(2);
    expect(component.selectedBot()?.published).toBe(true);
    expect(fixture.nativeElement.querySelector(".document-chat-step[hidden]")).toBeNull();
    expect(fixture.nativeElement.textContent).toContain("huong-dan.pdf");
  });

  it("lets workspace admins create with the workspace AI configuration", async () => {
    const { fixture } = await setup({}, "WORKSPACE_ADMIN");
    const component = openCreate(fixture);

    component.createChatbotAndContinue();
    fixture.detectChanges();

    expect(component.currentStep()).toBe(2);
    expect(fixture.nativeElement.querySelector(".advanced-toggle")).toBeNull();
  });

  it("applies a custom Gemini key before validating and creating", async () => {
    let credentialsUpdated = false;
    const { fixture } = await setup({
      updateProvider: vi.fn((id: string) => {
        credentialsUpdated = true;
        return of(id === embeddingProvider.id ? embeddingProvider : chatProvider);
      }),
      testProvider: vi.fn(() =>
        credentialsUpdated
          ? of({ status: "OK" })
          : throwError(() => new Error("old credentials")),
      ),
    });
    const component = openCreate(fixture);
    component.geminiApiKey = "new-key";

    component.createChatbotAndContinue();
    fixture.detectChanges();

    expect(component.currentStep()).toBe(2);
    expect(component.geminiApiKey).toBe("");
  });

  it("keeps chat disabled until a document is ready", async () => {
    const processingDocument = {
      ...readyDocument,
      status: "QUEUED",
      stage: "EMBEDDING",
      progress: 60,
    };
    const { fixture } = await setup({
      documents: vi.fn(() => of([processingDocument])),
    });
    const component = openCreate(fixture);
    component.createChatbotAndContinue();
    component.chatInput = "Nội dung tài liệu là gì?";
    fixture.detectChanges();

    const send = fixture.nativeElement.querySelector(
      ".chat-zone button.ant-btn-primary",
    ) as HTMLButtonElement;
    expect(send.disabled).toBe(true);

    component.documents.set([readyDocument]);
    fixture.detectChanges();
    expect(send.disabled).toBe(false);
  });

  it("uploads a file and refreshes the workspace document list", async () => {
    const documents = vi
      .fn()
      .mockReturnValueOnce(of([]))
      .mockReturnValueOnce(of([readyDocument]));
    const { fixture } = await setup({ documents });
    const component = openCreate(fixture);
    component.createChatbotAndContinue();

    component.beforeUpload(new File(["content"], "huong-dan.txt", { type: "text/plain" }));
    fixture.detectChanges();

    expect(component.documents()).toEqual([readyDocument]);
    expect(component.uploading()).toBe(false);
  });

  it("uses standard ng-zorro variants for document actions", async () => {
    const { fixture } = await setup({
      documents: vi.fn(() => of([readyDocument])),
    });
    const component = openCreate(fixture);
    component.createChatbotAndContinue();
    fixture.detectChanges();

    const reindex = fixture.nativeElement.querySelector(
      ".document-actions button:not(.ant-btn-dangerous)",
    ) as HTMLButtonElement;
    const remove = fixture.nativeElement.querySelector(
      ".document-actions .ant-btn-dangerous",
    ) as HTMLButtonElement;

    expect(reindex.classList).toContain("ant-btn-primary");
    expect(remove.classList).toContain("ant-btn-primary");
  });
});
