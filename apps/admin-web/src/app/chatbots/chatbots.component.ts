import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  signal,
} from "@angular/core";
import { DatePipe } from "@angular/common";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { FormsModule } from "@angular/forms";
import { ActivatedRoute } from "@angular/router";
import { forkJoin, of, switchMap, timer } from "rxjs";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzPopconfirmModule } from "ng-zorro-antd/popconfirm";
import { NzSelectModule } from "ng-zorro-antd/select";
import { NzTableModule } from "ng-zorro-antd/table";
import { NzTagModule } from "ng-zorro-antd/tag";
import { NzUploadFile, NzUploadModule } from "ng-zorro-antd/upload";

import { session } from "../core/api-auth.interceptor";
import {
  Chatbot,
  ChatbotInput,
  ChatStreamEvent,
  DocumentItem,
  Organization,
  ProviderConfig,
  RaghubApiService,
  Workspace,
} from "../core/raghub-api.service";
import { ingestionErrorMessage } from "../documents/ingestion-errors";
import { chatError } from "../core/api/chat-error";

interface Citation {
  document_name?: string;
  page?: number | null;
  excerpt?: string;
  rank?: number;
}

interface TranscriptMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

@Component({
  selector: "raghub-chatbots",
  imports: [
    DatePipe,
    FormsModule,
    NzAlertModule,
    NzButtonModule,
    NzInputModule,
    NzPopconfirmModule,
    NzSelectModule,
    NzTableModule,
    NzTagModule,
    NzUploadModule,
  ],
  templateUrl: "./chatbots.component.html",
  styleUrl: "./chatbots.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChatbotsComponent {
  protected readonly screen = signal<"list" | "editor" | "embed">("list");
  protected readonly chatbotPageSize = 10;
  protected readonly workspaceFilterOpen = signal(false);
  protected readonly publishingBotId = signal("");
  protected readonly embedCode = signal("");
  protected readonly embedBusy = signal(false);
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly providers = signal<ProviderConfig[]>([]);
  protected readonly uniqueProviders = computed(() => {
    const seen = new Set<string>();
    return this.providers()
      .filter((provider) => provider.enabled)
      .filter((provider) => {
        const identity = `${provider.provider_type}:${provider.capability}:${provider.model}`;
        if (seen.has(identity)) return false;
        seen.add(identity);
        return true;
      });
  });
  protected readonly bots = signal<Chatbot[]>([]);
  protected readonly selectedBot = signal<Chatbot | null>(null);
  protected readonly isAdmin = computed(
    () =>
      this.organizations().find((item) => item.id === this.selectedOrganization)
        ?.role === "ADMIN",
  );  protected readonly messages = signal<TranscriptMessage[]>([]);
  protected readonly error = signal("");
  protected readonly notice = signal("");
  protected readonly isStreaming = signal(false);
  protected readonly currentStep = signal<1 | 2 | 3>(1);
  protected readonly advancedOpen = signal(false);
  protected readonly documents = signal<DocumentItem[]>([]);
  protected readonly uploading = signal(false);
  protected readonly connectionBusy = signal(false);
  protected readonly botBusy = signal(false);
  protected readonly creationBusy = computed(
    () => this.connectionBusy() || this.botBusy(),
  );
  protected readonly hasReadyDocuments = computed(() =>
    this.documents().some((document) => document.status === "READY"),
  );
  protected readonly statusLabel = (status: string): string =>
    ({
      QUEUED: "Đang chờ",
      PARSING: "Đang đọc tài liệu",
      CHUNKING: "Đang chia đoạn",
      EMBEDDING: "Đang tạo embedding",
      INDEXING: "Đang lập chỉ mục",
      READY: "Sẵn sàng",
      FAILED: "Lỗi",
    })[status] ?? status;
  protected readonly statusColor = (status: string): string =>
    status === "READY" ? "green" : status === "FAILED" ? "red" : "blue";
  protected readonly beforeUpload = (file: NzUploadFile): boolean => {
    this.uploadDocument((file.originFileObj ?? file) as File);
    return false;
  };
  private verifiedConnection = "";
  private workspaceRevision = 0;

  protected invalidateConnection(): void {
    this.verifiedConnection = "";
    this.currentStep.set(1);
  }

  protected goBack(step: 1 | 2): void {
    if (!this.connectionBusy() && !this.botBusy() && !this.isStreaming()) {
      this.currentStep.set(step);
      this.clearMessages();
    }
  }

  protected selectWorkspace(workspaceId: string): void {
    this.workspaceFilterOpen.set(false);
    if (workspaceId === this.selectedWorkspace) return;
    this.selectedWorkspace = workspaceId;
    this.changeWorkspace();
  }

  protected workspaceName(workspaceId: string): string {
    return (
      this.workspaces().find((workspace) => workspace.id === workspaceId)?.name ??
      "—"
    );
  }

  protected openCreateChatbot(): void {
    if (!this.selectedWorkspace) return;
    this.selectedBot.set(null);
    this.botName = "Trợ lý tài liệu";
    this.botPrompt =
      "Trả lời bằng tiếng Việt, chỉ dựa trên tài liệu đã tải lên. Nếu không đủ thông tin, hãy nói rõ điều đó.";
    this.botRetrievalLimit = 5;
    this.currentStep.set(1);
    this.advancedOpen.set(false);
    this.clearMessages();
    this.screen.set("editor");
  }

  protected editChatbot(bot: Chatbot): void {
    this.selectBot(bot);
    this.currentStep.set(1);
    this.advancedOpen.set(false);
    this.clearMessages();
    this.screen.set("editor");
  }

  protected openEmbed(bot: Chatbot): void {
    this.selectBot(bot);
    if (bot.published) this.loadEmbedCode(bot.id);
    this.clearMessages();
    this.screen.set("embed");
  }

  protected backToEditor(): void {
    if (this.embedBusy()) return;
    this.clearMessages();
    this.currentStep.set(1);
    this.screen.set("editor");
  }

  protected openChatbotDocuments(bot: Chatbot): void {
    this.selectBot(bot);
    this.currentStep.set(2);
    this.clearMessages();
    this.screen.set("editor");
    this.loadDocuments();
  }

  protected backToChatbotList(): void {
    if (this.creationBusy() || this.uploading() || this.isStreaming() || this.embedBusy()) return;
    this.currentStep.set(1);
    this.advancedOpen.set(false);
    this.clearMessages();
    this.screen.set("list");
  }

  protected toggleAdvanced(): void {
    this.advancedOpen.update((open) => !open);
  }

  protected selectMainModel(providerId: string): void {
    this.selectedChatProvider = providerId;
    const chat = this.providers().find((provider) => provider.id === providerId);
    if (chat) {
      this.chatSource =
        this.providerSource(chat) === "Local" ? "local" : "gemini";
      const matchingEmbedding = this.uniqueProviders().find(
        (provider) =>
          provider.capability === "EMBEDDING" &&
          (this.providerSource(provider) === "Local" ? "local" : "gemini") ===
            this.chatSource,
      );
      if (matchingEmbedding)
        this.selectedEmbeddingProvider = matchingEmbedding.id;
    }
    this.invalidateConnection();
  }

  protected createChatbotAndContinue(): void {
    if (this.creationBusy()) return;
    if (!this.selectedWorkspace) {
      this.setError("Chọn workspace trước khi tạo chatbot.");
      return;
    }
    if (
      !this.botName.trim() ||
      !Number.isInteger(Number(this.botRetrievalLimit)) ||
      Number(this.botRetrievalLimit) < 1 ||
      Number(this.botRetrievalLimit) > 10
    ) {
      this.setError("Nhập tên chatbot và số đoạn tài liệu từ 1 đến 10.");
      return;
    }
    if (!this.isAdmin()) {
      this.persistBotAndOpenDocuments();
      return;
    }

    const embedding = this.selectedProvider("EMBEDDING");
    const chat = this.selectedProvider("CHAT");
    if (!embedding || !chat) {
      this.setError("Chưa có cấu hình AI phù hợp cho workspace này.");
      return;
    }

    const customGeminiKey = this.geminiApiKey.trim();
    if (customGeminiKey) {
      if (
        embedding.provider_type !== "GOOGLE_GEMINI" ||
        chat.provider_type !== "GOOGLE_GEMINI"
      ) {
        this.setError(
          "API Key khác chỉ dùng khi cả mô hình Chat và Embedding đều là Google Gemini.",
        );
        return;
      }

      const revision = this.workspaceRevision;
      this.clearMessages();
      this.connectionBusy.set(true);
      forkJoin({
        embedding: this.api.updateProvider(embedding.id, {
          secret: customGeminiKey,
        }),
        chat: this.api.updateProvider(chat.id, { secret: customGeminiKey }),
      }).subscribe({
        next: ({ embedding: updatedEmbedding, chat: updatedChat }) => {
          if (revision !== this.workspaceRevision) return;
          this.connectionBusy.set(false);
          this.geminiApiKey = "";
          this.providers.update((providers) =>
            providers.map((provider) => {
              if (provider.id === updatedEmbedding.id) return updatedEmbedding;
              if (provider.id === updatedChat.id) return updatedChat;
              return provider;
            }),
          );
          this.validateAiAndCreate(updatedEmbedding, updatedChat);
        },
        error: () => {
          if (revision !== this.workspaceRevision) return;
          this.connectionBusy.set(false);
          this.setError(
            "Không thể lưu Google Gemini API Key. Vui lòng kiểm tra key và thử lại.",
          );
        },
      });
      return;
    }

    this.validateAiAndCreate(embedding, chat);
  }

  private validateAiAndCreate(
    embedding: ProviderConfig,
    chat: ProviderConfig,
  ): void {
    const revision = this.workspaceRevision;
    this.clearMessages();
    this.connectionBusy.set(true);
    forkJoin({
      embedding: this.api.testProvider(embedding.id),
      chat: this.api.testProvider(chat.id),
    })
      .pipe(
        switchMap(() =>
          this.api.bindWorkspaceProviders(
            this.selectedWorkspace,
            embedding.id,
            chat.id,
          ),
        ),
      )
      .subscribe({
        next: () => {
          if (revision !== this.workspaceRevision) return;
          this.connectionBusy.set(false);
          this.verifiedConnection = `${this.selectedWorkspace}:${embedding.id}:${chat.id}`;
          this.persistBotAndOpenDocuments();
        },
        error: () => {
          if (revision !== this.workspaceRevision) return;
          this.connectionBusy.set(false);
          this.setError(
            this.providerSource(chat) === "Local"
              ? "Không thể kết nối mô hình AI local. Hãy kiểm tra dịch vụ và model."
              : "Không thể kết nối Google Gemini. Vui lòng kiểm tra API Key.",
          );
        },
      });
  }

  private persistBotAndOpenDocuments(): void {
    const revision = this.workspaceRevision;
    const bot = this.selectedBot();
    this.botBusy.set(true);
    const request = bot
      ? this.api.updateChatbot(bot.id, this.botPayload(true))
      : this.api.createChatbot(this.selectedWorkspace, this.botPayload(true));
    request.subscribe({
      next: (saved) => {
        if (revision !== this.workspaceRevision) return;
        this.botBusy.set(false);
        if (!bot) this.bots.update((items) => [...items, saved]);
        this.replaceBot(saved);
        this.currentStep.set(2);
        this.notice.set("Chatbot đã sẵn sàng. Hãy thêm tài liệu để bắt đầu hỏi đáp.");
        this.loadDocuments();
      },
      error: () => {
        if (revision !== this.workspaceRevision) return;
        this.botBusy.set(false);
        this.setError("Không thể tạo chatbot. Dữ liệu bạn đã nhập vẫn được giữ lại.");
      },
    });
  }

  protected continueConnection(): void {
    const embedding = this.selectedProvider("EMBEDDING");
    const chat = this.selectedProvider("CHAT");
    if (!embedding || !chat || this.connectionBusy()) return;
    const revision = this.workspaceRevision;
    const identity = `${this.selectedWorkspace}:${embedding.id}:${chat.id}`;
    this.clearMessages();
    this.connectionBusy.set(true);
    this.connectionChecks.set({
      [embedding.id]: "Đang kiểm tra…",
      [chat.id]: "Đang kiểm tra…",
    });
    forkJoin({
      embedding: this.api.testProvider(embedding.id),
      chat: this.api.testProvider(chat.id),
    })
      .pipe(
        switchMap(() =>
          this.api.bindWorkspaceProviders(
            this.selectedWorkspace,
            embedding.id,
            chat.id,
          ),
        ),
      )
      .subscribe({
        next: () => {
          if (revision !== this.workspaceRevision) return;
          this.connectionBusy.set(false);
          this.connectionChecks.set({
            [embedding.id]: "Kết nối thành công",
            [chat.id]: "Kết nối thành công",
          });
          this.verifiedConnection = identity;
          this.currentStep.set(2);
          this.notice.set(
            "Đã kiểm tra và lưu kết nối AI. Tiếp theo, tạo và xuất bản chatbot.",
          );
        },
        error: () => {
          if (revision !== this.workspaceRevision) return;
          this.connectionBusy.set(false);
          this.connectionChecks.set({});
          this.verifiedConnection = "";
          this.setError(
            "Chưa thể hoàn tất kết nối AI. Kiểm tra từng kết nối Embedding và Chat rồi thử lại.",
          );
        },
      });
  }

  protected continueBot(): void {
    if (this.botBusy()) return;
    if (
      this.isAdmin() &&
      this.verifiedConnection !==
        `${this.selectedWorkspace}:${this.selectedEmbeddingProvider}:${this.selectedChatProvider}`
    )
      return;
    if (
      !this.botName.trim() ||
      !Number.isInteger(Number(this.botRetrievalLimit)) ||
      Number(this.botRetrievalLimit) < 1 ||
      Number(this.botRetrievalLimit) > 10
    ) {
      this.setError("Nhập tên chatbot và số đoạn tài liệu từ 1 đến 10.");
      return;
    }
    const revision = this.workspaceRevision;
    const bot = this.selectedBot();
    this.clearMessages();
    this.botBusy.set(true);
    const request = bot
      ? this.api.updateChatbot(bot.id, this.botPayload(true))
      : this.api.createChatbot(this.selectedWorkspace, this.botPayload(true));
    request.subscribe({
      next: (saved) => {
        if (revision !== this.workspaceRevision) return;
        this.botBusy.set(false);
        if (!bot) this.bots.update((items) => [...items, saved]);
        this.replaceBot(saved);
        if (saved.published) this.currentStep.set(3);
      },
      error: () => {
        if (revision !== this.workspaceRevision) return;
        this.botBusy.set(false);
        this.setError("Không thể lưu và xuất bản chatbot. Hãy thử lại.");
      },
    });
  }

  protected selectedOrganization = session.organizationId ?? "";
  protected selectedWorkspace = "";
  protected selectedEmbeddingProvider = "";
  protected selectedChatProvider = "";
  protected embeddingSource: "local" | "gemini" = "local";
  protected chatSource: "local" | "gemini" = "gemini";
  protected connectionMode: "local" | "api" = "local";
  protected readonly connectionChecks = signal<Record<string, string>>({});
  protected readonly providerRefreshBusy = signal(false);
  protected showGeminiForm = false;
  protected localChatModel = "gemma3:1b";
  protected providerSource(provider: ProviderConfig): string {
    return [
      "OLLAMA",
      "LOCAL_SENTENCE_TRANSFORMER",
      "LOCAL_TOKEN_HASH",
    ].includes(provider.provider_type)
      ? "Local"
      : "API";
  }
  protected readonly localEmbeddingModel =
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2";
  protected geminiApiKey = "";
  protected geminiChatModel = "gemini-3.5-flash-lite";
  protected botName = "Trợ lý tài liệu";
  protected botPrompt =
    "Trả lời bằng tiếng Việt, chỉ dựa trên tài liệu đã tải lên. Nếu không đủ thông tin, hãy nói rõ điều đó.";
  protected botRetrievalLimit = 5;
  protected embedOrigins = location.origin;
  protected embedPrimaryColor = "#1463ff";
  protected embedTitle = "RagHub Assistant";
  protected embedGreeting = "Xin chào! Tôi có thể giúp gì cho bạn?";
  protected chatInput = "";
  private conversationId: string | null = null;
  private readonly api = inject(RaghubApiService);
  private readonly requestedWorkspaceId =
    inject(ActivatedRoute).snapshot.queryParamMap.get("workspaceId") ?? "";
  private readonly destroyRef = inject(DestroyRef);

  protected providersFor(capability: "EMBEDDING" | "CHAT"): ProviderConfig[] {
    const source =
      capability === "EMBEDDING" ? this.embeddingSource : this.chatSource;
    return this.uniqueProviders().filter(
      (provider) =>
        provider.capability === capability &&
        (source === "gemini"
          ? provider.provider_type === "GOOGLE_GEMINI"
          : this.providerSource(provider) === "Local"),
    );
  }

  protected setProviderSource(
    capability: "EMBEDDING" | "CHAT",
    source: "local" | "gemini",
  ): void {
    if (capability === "EMBEDDING") this.embeddingSource = source;
    else this.chatSource = source;
    const first = this.providersFor(capability)[0];
    if (capability === "EMBEDDING")
      this.selectedEmbeddingProvider = first?.id ?? "";
    else this.selectedChatProvider = first?.id ?? "";
    this.invalidateConnection();
  }

  protected providerLabel(provider: ProviderConfig): string {
    const source =
      this.providerSource(provider) === "Local" ? "Local" : "Gemini";
    return `[${source}] ${provider.model}`;
  }

  protected chatProviderOptions(): ProviderConfig[] {
    return this.uniqueProviders().filter(
      (provider) => provider.capability === "CHAT",
    );
  }

  protected embeddingProviderOptions(): ProviderConfig[] {
    return this.uniqueProviders().filter(
      (provider) => provider.capability === "EMBEDDING",
    );
  }

  protected onChatProviderChange(providerId: string): void {
    this.selectedChatProvider = providerId;
    this.invalidateConnection();
  }

  protected onEmbeddingProviderChange(providerId: string): void {
    this.selectedEmbeddingProvider = providerId;
    this.invalidateConnection();
  }

  protected providerCount(type: ProviderConfig["provider_type"]): number {
    return this.uniqueProviders().filter(
      (provider) => provider.provider_type === type,
    ).length;
  }

  protected refreshProviderChoices(): void {
    if (!this.selectedOrganization || this.providerRefreshBusy()) return;
    this.providerRefreshBusy.set(true);
    this.api.providers(this.selectedOrganization).subscribe({
      next: (items) => {
        this.providers.set(items);
        this.autoSelectProviders();
        this.providerRefreshBusy.set(false);
        this.notice.set("Đã làm mới danh sách model từ backend.");
      },
      error: () => {
        this.providerRefreshBusy.set(false);
        this.setError("Không thể làm mới danh sách model từ backend.");
      },
    });
  }

  protected testSelected(capability: "EMBEDDING" | "CHAT"): void {
    const provider = this.selectedProvider(capability);
    if (provider) this.testProvider(provider);
  }

  constructor() {
    this.loadOrganizations();
    timer(3000, 3000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (
          this.currentStep() === 2 &&
          this.documents().some(
            (document) => !["READY", "FAILED"].includes(document.status),
          )
        ) {
          this.loadDocuments();
        }
      });
  }

  protected loadOrganizations(): void {
    this.api.organizations().subscribe({
      next: (items) => {
        this.organizations.set(items);
        if (!this.selectedOrganization && items[0])
          this.selectedOrganization = items[0].id;
        this.changeOrganization();
      },
      error: () =>
        this.setError(
          "Hãy đăng nhập và chọn tổ chức trước khi cấu hình chatbot.",
        ),
    });
  }

  protected changeOrganization(): void {
    session.organizationId = this.selectedOrganization || null;
    this.resetWorkspaceState();
    if (!this.selectedOrganization) return;
    this.api.workspaces().subscribe({
      next: (items) => {
        this.workspaces.set(items);
        this.selectedWorkspace =
          items.find((workspace) => workspace.id === this.requestedWorkspaceId)
            ?.id ??
          items[0]?.id ??
          "";
        this.changeWorkspace();
      },
      error: () =>
        this.setError("Không thể tải không gian làm việc của tổ chức này."),
    });
  }

  protected changeWorkspace(): void {
    this.workspaceRevision++;
    this.invalidateConnection();
    this.currentStep.set(1);
    this.advancedOpen.set(false);
    this.connectionBusy.set(false);
    this.botBusy.set(false);
    this.connectionChecks.set({});
    this.selectedEmbeddingProvider = "";
    this.selectedChatProvider = "";
    this.clearMessages();
    this.providers.set([]);
    this.bots.set([]);
    this.selectedBot.set(null);
    this.messages.set([]);
    this.documents.set([]);
    this.conversationId = null;
    if (!this.selectedWorkspace || !this.selectedOrganization) return;
    if (this.isAdmin()) {
      this.api.providers(this.selectedOrganization).subscribe({
        next: (items) => {
          this.providers.set(items);
          this.autoSelectProviders();
        },
        error: () => this.setError("Không thể tải danh sách nhà cung cấp AI."),
      });
    }
    this.api.chatbots(this.selectedWorkspace).subscribe({
      next: (items) => {
        this.bots.set(items);
        this.selectedBot.set(null);
      },
      error: () =>
        this.setError("Không thể tải chatbot của không gian làm việc."),
    });
  }

  protected configureLocal(): void {
    this.invalidateConnection();
    if (!this.selectedOrganization || !this.selectedWorkspace) return;
    this.clearMessages();
    const current = this.uniqueProviders();
    const embedding = current.find(
      (provider) =>
        provider.provider_type === "LOCAL_SENTENCE_TRANSFORMER" &&
        provider.capability === "EMBEDDING" &&
        provider.model === this.localEmbeddingModel,
    );
    const chat = current.find(
      (provider) =>
        provider.provider_type === "OLLAMA" &&
        provider.capability === "CHAT" &&
        provider.model === this.localChatModel,
    );
    forkJoin({
      embedding: embedding
        ? of(embedding)
        : this.api.createProvider(this.selectedOrganization, {
            name: "Embedding local",
            provider_type: "LOCAL_SENTENCE_TRANSFORMER",
            capability: "EMBEDDING",
            model: this.localEmbeddingModel,
            dimension: 384,
          }),
      chat: chat
        ? of(chat)
        : this.api.createProvider(this.selectedOrganization, {
            name: "Chat Ollama",
            provider_type: "OLLAMA",
            capability: "CHAT",
            model: this.localChatModel,
            base_url: "http://ollama:11434",
          }),
    }).subscribe({
      next: ({ embedding: embeddingProvider, chat: chatProvider }) => {
        this.selectedEmbeddingProvider = embeddingProvider.id;
        this.selectedChatProvider = chatProvider.id;
        this.reloadProviders();
        this.notice.set(
          "Đã thêm model local vào danh sách. Chọn model ở phần bên dưới rồi kiểm tra.",
        );
      },
      error: () =>
        this.setError(
          "Không thể tạo provider local. Kiểm tra Ollama, model và nhật ký API.",
        ),
    });
  }

  protected configureGemini(): void {
    this.invalidateConnection();
    if (
      !this.selectedOrganization ||
      !this.selectedWorkspace ||
      !this.geminiApiKey.trim()
    ) {
      this.setError("Nhập Gemini API key trước khi cấu hình Gemini.");
      return;
    }
    this.clearMessages();
    const baseUrl = "https://generativelanguage.googleapis.com/v1beta/openai";
    const current = this.uniqueProviders();
    // Tái dùng provider cùng model để tránh tạo trùng mỗi lần bấm Lưu (lỗi 3 dòng Chat Gemini giống hệt nhau).
    const embeddingModel = "gemini-embedding-2";
    const existingEmbedding = current.find(
      (provider) =>
        provider.provider_type === "GOOGLE_GEMINI" &&
        provider.capability === "EMBEDDING" &&
        provider.model === embeddingModel,
    );
    const existingChat = current.find(
      (provider) =>
        provider.provider_type === "GOOGLE_GEMINI" &&
        provider.capability === "CHAT" &&
        provider.model === this.geminiChatModel,
    );
    forkJoin({
      embedding: existingEmbedding
        ? this.api.updateProvider(existingEmbedding.id, {
            secret: this.geminiApiKey,
          })
        : this.api.createProvider(this.selectedOrganization, {
            name: "Embedding Gemini",
            provider_type: "GOOGLE_GEMINI",
            capability: "EMBEDDING",
            base_url: baseUrl,
            model: embeddingModel,
            dimension: 3072,
            secret: this.geminiApiKey,
          }),
      chat: existingChat
        ? this.api.updateProvider(existingChat.id, {
            secret: this.geminiApiKey,
          })
        : this.api.createProvider(this.selectedOrganization, {
            name: "Chat Gemini",
            provider_type: "GOOGLE_GEMINI",
            capability: "CHAT",
            base_url: baseUrl,
            model: this.geminiChatModel,
            secret: this.geminiApiKey,
          }),
    }).subscribe({
      next: ({ embedding, chat }) => {
        this.geminiApiKey = "";
        this.selectedEmbeddingProvider = embedding.id;
        this.selectedChatProvider = chat.id;
        this.reloadProviders();
        this.notice.set(
          "Đã thêm Gemini vào danh sách model. Chọn model ở phần bên dưới rồi kiểm tra.",
        );
      },
      error: () =>
        this.setError(
          "Không thể lưu Gemini. Kiểm tra API key và model rồi thử lại.",
        ),
    });
  }

  protected bindProviders(): void {
    this.invalidateConnection();
    if (
      !this.selectedWorkspace ||
      !this.selectedEmbeddingProvider ||
      !this.selectedChatProvider
    ) {
      this.setError("Chọn cả embedding và chat provider trước khi lưu.");
      return;
    }
    this.api
      .bindWorkspaceProviders(
        this.selectedWorkspace,
        this.selectedEmbeddingProvider,
        this.selectedChatProvider,
      )
      .subscribe({
        next: () => {
          this.notice.set(
            "Provider đã được gắn vào workspace. Tài liệu READY có thể dùng để hỏi đáp.",
          );
          this.error.set("");
          this.reloadProviders();
        },
        error: () =>
          this.setError(
            "Không thể gắn provider vào workspace. Hãy kiểm tra quyền và provider đã tạo.",
          ),
      });
  }

  protected testProvider(provider: ProviderConfig): void {
    this.clearMessages();
    this.connectionChecks.update((checks) => ({
      ...checks,
      [provider.id]: "Đang kiểm tra…",
    }));
    this.api.testProvider(provider.id).subscribe({
      next: () => {
        this.connectionChecks.update((checks) => ({
          ...checks,
          [provider.id]: "Kết nối thành công",
        }));
        this.notice.set(`Kết nối ${provider.name} hoạt động.`);
      },
      error: () => {
        this.connectionChecks.update((checks) => ({
          ...checks,
          [provider.id]: "Kết nối thất bại",
        }));
        this.setError(
          this.providerSource(provider) === "Local"
            ? `Không thể kết nối ${provider.name}. Kiểm tra dịch vụ local và model đã cài.`
            : `Không thể kết nối ${provider.name}. Kiểm tra API key, model và mạng.`,
        );
      },
    });
  }

  protected createBot(): void {
    if (!this.selectedWorkspace || !this.botName.trim()) return;
    this.clearMessages();
    const payload = this.botPayload(false);
    this.api.createChatbot(this.selectedWorkspace, payload).subscribe({
      next: (bot) => {
        this.bots.update((items) => [...items, bot]);
        this.selectBot(bot);
        this.notice.set("Chatbot đã được tạo. Hãy xuất bản để thử chat.");
      },
      error: () =>
        this.setError(
          "Không thể tạo chatbot. Hãy cấu hình provider trước và kiểm tra quyền workspace.",
        ),
    });
  }

  protected saveBot(): void {
    const bot = this.selectedBot();
    if (!bot) return this.createBot();
    this.clearMessages();
    this.api.updateChatbot(bot.id, this.botPayload(bot.published)).subscribe({
      next: (saved) => this.replaceBot(saved),
      error: () => this.setError("Không thể lưu thay đổi chatbot."),
    });
  }

  protected saveEmbedSettings(): void {
    const bot = this.selectedBot();
    if (!bot || this.embedBusy()) return;
    const allowedOrigins = this.embedOrigins
      .split(/\n|,/)
      .map((value) => value.trim())
      .filter(Boolean);
    if (!allowedOrigins.length) {
      this.setError("Nhập ít nhất một website được phép nhúng chatbot.");
      return;
    }

    this.clearMessages();
    this.embedBusy.set(true);
    this.api
      .publishEmbed(bot.id, {
        allowed_origins: allowedOrigins,
        primary_color: this.embedPrimaryColor,
        title: this.embedTitle.trim(),
        greeting: this.embedGreeting.trim(),
      })
      .subscribe({
        next: (result) => {
          this.embedBusy.set(false);
          this.embedCode.set(result.code);
          const updated: Chatbot = {
            ...bot,
            published: true,
            allowed_origins: allowedOrigins,
            embed_primary_color: this.embedPrimaryColor,
            embed_title: this.embedTitle.trim(),
            embed_greeting: this.embedGreeting.trim(),
          };
          this.selectedBot.set(updated);
          this.bots.update((items) =>
            items.map((item) => (item.id === updated.id ? updated : item)),
          );
          this.notice.set(
            "Đã lưu cấu hình nhúng và xuất bản chatbot. Hãy sao chép mã nhúng ngay.",
          );
        },
        error: (response) => {
          this.embedBusy.set(false);
          this.setError(
            response?.error?.error?.message ||
              "Không thể lưu cấu hình nhúng chatbot.",
          );
        },
      });
  }

  protected rotateEmbedKey(): void {
    const bot = this.selectedBot();
    if (!bot || !bot.published || this.embedBusy()) return;
    this.clearMessages();
    this.embedBusy.set(true);
    this.api.rotateEmbedKey(bot.id).subscribe({
      next: (result) => {
        this.embedBusy.set(false);
        this.embedCode.set(result.code);
        this.notice.set("Đã tạo key mới. Mã nhúng cũ không còn hoạt động.");
      },
      error: () => {
        this.embedBusy.set(false);
        this.setError("Không thể tạo key nhúng mới.");
      },
    });
  }

  protected async copyEmbedCode(): Promise<void> {
    if (!this.embedCode()) return;
    await navigator.clipboard?.writeText(this.embedCode());
    this.notice.set("Đã sao chép mã nhúng.");
    this.error.set("");
  }

  private loadEmbedCode(chatbotId: string): void {
    this.embedCode.set("");
    this.api.embedCode(chatbotId).subscribe({
      next: (result) => this.embedCode.set(result.code),
      error: () => this.embedCode.set(""),
    });
  }

  protected toggleBotPublish(bot: Chatbot): void {
    if (this.publishingBotId()) return;
    this.clearMessages();
    this.publishingBotId.set(bot.id);
    this.api.updateChatbot(bot.id, { published: !bot.published }).subscribe({
      next: (saved) => {
        this.publishingBotId.set("");
        this.bots.update((items) =>
          items.map((item) => (item.id === saved.id ? saved : item)),
        );
        if (this.selectedBot()?.id === saved.id) this.selectedBot.set(saved);
        this.notice.set(
          saved.published
            ? "Chatbot đã được xuất bản."
            : "Chatbot đã chuyển về bản nháp.",
        );
        this.error.set("");
      },
      error: () => {
        this.publishingBotId.set("");
        this.setError("Không thể đổi trạng thái xuất bản.");
      },
    });
  }

  protected loadDocuments(): void {
    if (!this.selectedWorkspace) {
      this.documents.set([]);
      return;
    }
    this.api.documents(this.selectedWorkspace).subscribe({
      next: (items) => this.documents.set(items),
      error: () => this.setError("Không thể tải danh sách tài liệu của workspace."),
    });
  }

  protected uploadDocument(file: File): void {
    if (!this.selectedWorkspace || this.uploading()) return;
    this.uploading.set(true);
    this.api.upload(this.selectedWorkspace, file).subscribe({
      next: () => {
        this.uploading.set(false);
        this.notice.set("Đã tải tài liệu lên. Hệ thống đang xử lý tài liệu.");
        this.loadDocuments();
      },
      error: (response) => {
        this.uploading.set(false);
        this.setError(ingestionErrorMessage(response.error?.error?.code));
      },
    });
  }

  protected retryDocument(document: DocumentItem): void {
    if (!document.document_version_id || !document.retryable) return;
    this.api
      .retryDocument(this.selectedWorkspace, document.document_version_id)
      .subscribe({
        next: () => this.loadDocuments(),
        error: (response) =>
          this.setError(ingestionErrorMessage(response.error?.error?.code)),
      });
  }

  protected reindexDocument(document: DocumentItem): void {
    if (!document.document_version_id || document.status !== "READY") return;
    this.api
      .reindexDocument(this.selectedWorkspace, document.document_version_id)
      .subscribe({
        next: () => this.loadDocuments(),
        error: (response) =>
          this.setError(ingestionErrorMessage(response.error?.error?.code)),
      });
  }

  protected removeDocument(document: DocumentItem): void {
    this.api.deleteDocument(this.selectedWorkspace, document.id).subscribe({
      next: () =>
        this.documents.update((items) =>
          items.filter((item) => item.id !== document.id),
        ),
      error: () => this.setError("Không thể xóa tài liệu."),
    });
  }

  protected selectBot(bot: Chatbot | null): void {
    this.selectedBot.set(bot);
    this.messages.set([]);
    this.conversationId = null;
    this.embedCode.set("");
    if (!bot) return;
    this.botName = bot.name;
    this.botPrompt = bot.system_prompt;
    this.botRetrievalLimit = bot.retrieval_limit;
    this.embedOrigins = bot.allowed_origins?.join("\n") || location.origin;
    this.embedPrimaryColor = bot.embed_primary_color || "#1463ff";
    this.embedTitle = bot.embed_title || bot.name;
    this.embedGreeting =
      bot.embed_greeting || "Xin chào! Tôi có thể giúp gì cho bạn?";
  }

  protected send(): void {
    const bot = this.selectedBot();
    const question = this.chatInput.trim();
    if (
      this.currentStep() !== 2 ||
      !bot ||
      !bot.published ||
      !this.hasReadyDocuments() ||
      !question ||
      this.isStreaming()
    )
      return;
    this.clearMessages();
    this.chatInput = "";
    this.isStreaming.set(true);
    this.messages.set([
      { role: "user", content: question },
      { role: "assistant", content: "" },
    ]);
    void this.api.streamChat(
      bot.id,
      { message: question, conversation_id: this.conversationId },
      (event) => this.handleStream(event),
    );
  }

  protected citationLabel(citation: Citation): string {
    return `${citation.document_name ?? "Tài liệu"}${citation.page ? ` · trang ${citation.page}` : ""}`;
  }

  private handleStream(event: ChatStreamEvent): void {
    if (
      event.event === "conversation" &&
      typeof event.data["conversation_id"] === "string"
    )
      this.conversationId = event.data["conversation_id"];
    if (event.event === "token" && typeof event.data["text"] === "string")
      this.updateAssistant((message) => ({
        ...message,
        content: message.content + event.data["text"],
      }));
    if (event.event === "citations" && Array.isArray(event.data["citations"]))
      this.updateAssistant((message) => ({
        ...message,
        citations: event.data["citations"] as Citation[],
      }));
    if (event.event === "error")
      this.setError(chatError(event.data));
    if (event.event === "done" || event.event === "error")
      this.isStreaming.set(false);
  }

  private updateAssistant(
    update: (message: TranscriptMessage) => TranscriptMessage,
  ): void {
    this.messages.update((items) =>
      items.map((message, index) =>
        index === items.length - 1 ? update(message) : message,
      ),
    );
  }

  private botPayload(published: boolean): ChatbotInput {
    return {
      name: this.botName.trim(),
      system_prompt: this.botPrompt.trim(),
      retrieval_limit: Number(this.botRetrievalLimit),
      published,
    };
  }

  private replaceBot(saved: Chatbot): void {
    this.bots.update((items) =>
      items.map((item) => (item.id === saved.id ? saved : item)),
    );
    this.selectedBot.set(saved);
    this.notice.set("Đã lưu chatbot.");
    this.error.set("");
  }

  private reloadProviders(): void {
    if (!this.selectedOrganization || !this.isAdmin()) return;
    this.api.providers(this.selectedOrganization).subscribe({
      next: (items) => {
        this.providers.set(items);
        this.autoSelectProviders();
      },
    });
  }

  private autoSelectProviders(): void {
    const items = this.uniqueProviders();
    const embeddings = items.filter(
      (provider) => provider.capability === "EMBEDDING",
    );
    const chats = items.filter((provider) => provider.capability === "CHAT");
    const sourceOf = (provider: ProviderConfig) =>
      this.providerSource(provider) === "Local" ? "local" : "gemini";
    if (
      !embeddings.some(
        (provider) => sourceOf(provider) === this.embeddingSource,
      ) &&
      embeddings[0]
    ) {
      this.embeddingSource = sourceOf(embeddings[0]);
    }
    if (
      !chats.some((provider) => sourceOf(provider) === this.chatSource) &&
      chats[0]
    ) {
      this.chatSource = sourceOf(chats[0]);
    }
    if (
      !embeddings.some(
        (provider) =>
          provider.id === this.selectedEmbeddingProvider &&
          sourceOf(provider) === this.embeddingSource,
      )
    ) {
      this.selectedEmbeddingProvider =
        embeddings.find(
          (provider) => sourceOf(provider) === this.embeddingSource,
        )?.id ?? "";
    }
    if (
      !chats.some(
        (provider) =>
          provider.id === this.selectedChatProvider &&
          sourceOf(provider) === this.chatSource,
      )
    ) {
      this.selectedChatProvider =
        chats.find((provider) => sourceOf(provider) === this.chatSource)?.id ??
        "";
    }
  }

  protected isActiveProvider(providerId: string): boolean {
    return (
      providerId === this.selectedEmbeddingProvider ||
      providerId === this.selectedChatProvider
    );
  }

  protected selectedProvider(
    capability: "EMBEDDING" | "CHAT",
  ): ProviderConfig | undefined {
    const providerId =
      capability === "EMBEDDING"
        ? this.selectedEmbeddingProvider
        : this.selectedChatProvider;
    return this.providers().find((provider) => provider.id === providerId);
  }

  private resetWorkspaceState(): void {
    this.workspaces.set([]);
    this.providers.set([]);
    this.bots.set([]);
    this.selectedWorkspace = "";
    this.selectedBot.set(null);
    this.messages.set([]);
    this.documents.set([]);
    this.conversationId = null;
  }

  private clearMessages(): void {
    this.error.set("");
    this.notice.set("");
  }
  private setError(message: string): void {
    this.error.set(message);
    this.notice.set("");
  }
}
