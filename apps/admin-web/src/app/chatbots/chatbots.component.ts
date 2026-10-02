import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
import { RouterLink } from "@angular/router";
import { forkJoin, of, switchMap } from "rxjs";

import { session } from "../core/api-auth.interceptor";
import {
  Chatbot,
  ChatbotInput,
  ChatStreamEvent,
  Organization,
  ProviderConfig,
  RaghubApiService,
  Workspace,
} from "../core/raghub-api.service";

interface Citation {
  document_name?: string;
  page_number?: number | null;
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
  imports: [FormsModule, RouterLink],
  templateUrl: "./chatbots.component.html",
  styleUrl: "./chatbots.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChatbotsComponent {
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
  protected readonly connectionBusy = signal(false);
  protected readonly botBusy = signal(false);
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
  protected chatInput = "";
  private conversationId: string | null = null;
  private readonly api = inject(RaghubApiService);

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
        this.selectedWorkspace = items[0]?.id ?? "";
        this.changeWorkspace();
      },
      error: () =>
        this.setError("Không thể tải không gian làm việc của tổ chức này."),
    });
  }

  protected changeWorkspace(): void {
    this.workspaceRevision++;
    this.invalidateConnection();
    this.currentStep.set(this.isAdmin() ? 1 : 2);
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
        const published =
          items.find((bot) => bot.published) ?? items[0] ?? null;
        this.selectBot(published);
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

  protected togglePublish(): void {
    const bot = this.selectedBot();
    if (!bot) return;
    this.clearMessages();
    this.api.updateChatbot(bot.id, { published: !bot.published }).subscribe({
      next: (saved) => {
        this.replaceBot(saved);
        this.notice.set(
          saved.published
            ? "Chatbot đã được xuất bản."
            : "Chatbot đã chuyển về bản nháp.",
        );
      },
      error: () => this.setError("Không thể đổi trạng thái xuất bản."),
    });
  }

  protected selectBot(bot: Chatbot | null): void {
    this.selectedBot.set(bot);
    this.messages.set([]);
    this.conversationId = null;
    if (!bot) return;
    this.botName = bot.name;
    this.botPrompt = bot.system_prompt;
    this.botRetrievalLimit = bot.retrieval_limit;
  }

  protected send(): void {
    const bot = this.selectedBot();
    const question = this.chatInput.trim();
    if (
      this.currentStep() !== 3 ||
      !bot ||
      !bot.published ||
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
    return `${citation.document_name ?? "Tài liệu"}${citation.page_number ? ` · trang ${citation.page_number}` : ""}`;
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
      this.setError(
        typeof event.data["message"] === "string"
          ? event.data["message"]
          : "Chatbot gặp lỗi khi tạo câu trả lời.",
      );
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
