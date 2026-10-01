import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { forkJoin, of, timer } from 'rxjs';

import { session } from '../core/api-auth.interceptor';
import {
  Chatbot,
  ChatbotInput,
  ChatStreamEvent,
  DocumentItem,
  Organization,
  ProviderConfig,
  RaghubApiService,
  Workspace,
} from '../core/raghub-api.service';
import { ingestionErrorMessage } from '../documents/ingestion-errors';

interface Citation { document_id?: string; document_name?: string; page_number?: number | null; excerpt?: string; rank?: number; }
interface TranscriptMessage { role: 'user' | 'assistant'; content: string; citations?: Citation[]; }

@Component({
  selector: 'raghub-workspace-console',
  imports: [FormsModule, RouterLink],
  templateUrl: './workspace-console.component.html',
  styleUrl: './workspace-console.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceConsoleComponent {
  protected readonly ingestionErrorMessage = ingestionErrorMessage;
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly providers = signal<ProviderConfig[]>([]);
  protected readonly documents = signal<DocumentItem[]>([]);
  protected readonly bots = signal<Chatbot[]>([]);
  protected readonly selectedBot = signal<Chatbot | null>(null);
  protected readonly messages = signal<TranscriptMessage[]>([]);
  protected readonly isStreaming = signal(false);
  protected readonly setupOpen = signal(false);
  protected readonly selectedDocumentId = signal('');
  protected readonly reindexingVersionId = signal('');
  protected readonly statusLabel = (status: string): string => ({
    QUEUED: 'Đang chờ', PARSING: 'Đang đọc tài liệu', CHUNKING: 'Đang chia đoạn',
    EMBEDDING: 'Đang tạo embedding', INDEXING: 'Đang lập chỉ mục', READY: 'Sẵn sàng', FAILED: 'Thất bại',
  })[status] ?? status;
  protected readonly hasReadyDocument = computed(() =>
    this.documents().some((item) => item.status === 'READY'),
  );
  protected readonly hasChatProvider = computed(() =>
    this.providers().some((item) => item.capability === 'CHAT' && item.enabled),
  );
  protected readonly hasPublishedBot = computed(() => Boolean(this.selectedBot()?.published));
  protected readonly error = signal('');
  protected selectedOrganization = session.organizationId ?? '';
  protected selectedWorkspace = '';
  protected localChatModel = 'gemma3:4b';
  protected geminiApiKey = '';
  protected geminiChatModel = 'gemini-3.5-flash-lite';
  protected botName = 'Trợ lý tài liệu';
  protected botPrompt = 'Trả lời bằng tiếng Việt, chỉ dựa trên tài liệu đã tải lên.';
  protected botRetrievalLimit = 5;
  protected chatInput = '';
  protected readonly fileInput = viewChild<ElementRef<HTMLInputElement>>('fileInput');
  private readonly api = inject(RaghubApiService);
  private readonly destroyRef = inject(DestroyRef);
  private conversationId: string | null = null;

  constructor() {
    this.api.organizations().subscribe({
      next: (items) => {
        this.organizations.set(items);
        if (!this.selectedOrganization && items[0]) this.selectedOrganization = items[0].id;
        this.changeOrganization();
      },
      error: () => this.error.set('Hãy đăng nhập và chọn một tổ chức trước khi mở workspace.'),
    });
    timer(3000, 3000).pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      if (this.documents().some((item) => !['READY', 'FAILED'].includes(item.status))) this.loadDocuments();
    });
  }

  protected changeOrganization(): void {
    session.organizationId = this.selectedOrganization || null;
    this.workspaces.set([]);
    this.selectedWorkspace = '';
    if (!this.selectedOrganization) return;
    this.api.workspaces().subscribe({
      next: (items) => {
        this.workspaces.set(items);
        this.selectedWorkspace = items[0]?.id ?? '';
        this.changeWorkspace();
      },
      error: () => this.error.set('Không thể tải danh sách không gian làm việc.'),
    });
  }

  protected changeWorkspace(): void {
    this.providers.set([]);
    this.documents.set([]);
    this.bots.set([]);
    this.selectedBot.set(null);
    this.selectedDocumentId.set('');
    this.messages.set([]);
    this.conversationId = null;
    if (!this.selectedOrganization || !this.selectedWorkspace) return;
    this.api.providers(this.selectedOrganization).subscribe({
      next: (items) => this.providers.set(items),
      error: () => this.error.set('Không thể tải cấu hình AI của tổ chức.'),
    });
    this.loadDocuments();
    this.api.chatbots(this.selectedWorkspace).subscribe({
      next: (items) => {
        this.bots.set(items);
        this.selectBot(items.find((bot) => bot.published) ?? items[0] ?? null);
      },
      error: () => this.error.set('Không thể tải chatbot của workspace.'),
    });
  }

  protected upload(): void {
    const file = this.fileInput()?.nativeElement.files?.[0];
    if (!file || !this.selectedWorkspace) return;
    this.api.upload(this.selectedWorkspace, file).subscribe({
      next: () => this.loadDocuments(),
      error: (response) => this.error.set(ingestionErrorMessage(response.error?.error?.code)),
    });
  }

  protected retry(document: DocumentItem): void {
    if (!document.document_version_id || !document.retryable) return;
    this.api.retryDocument(this.selectedWorkspace, document.document_version_id).subscribe({
      next: () => this.loadDocuments(),
      error: (response) => this.error.set(ingestionErrorMessage(response.error?.error?.code)),
    });
  }

  protected reindex(document: DocumentItem): void {
    if (!document.document_version_id || document.status !== 'READY') return;
    this.reindexingVersionId.set(document.document_version_id);
    this.api.reindexDocument(this.selectedWorkspace, document.document_version_id).subscribe({
      next: () => { this.reindexingVersionId.set(''); this.loadDocuments(); },
      error: (response) => { this.reindexingVersionId.set(''); this.error.set(ingestionErrorMessage(response.error?.error?.code)); },
    });
  }

  protected remove(document: DocumentItem): void {
    if (!this.selectedWorkspace) return;
    this.api.deleteDocument(this.selectedWorkspace, document.id).subscribe({
      next: () => this.documents.update((items) => items.filter((item) => item.id !== document.id)),
      error: () => this.error.set('Không thể xóa tài liệu.'),
    });
  }

  protected selectDocument(documentId: string): void { this.selectedDocumentId.set(documentId); }

  protected toggleSetup(): void { this.setupOpen.update((open) => !open); }

  protected configureLocal(): void {
    if (!this.selectedOrganization || !this.selectedWorkspace) return;
    const current = this.providers();
    const embedding = current.find((provider) => provider.provider_type === 'LOCAL_SENTENCE_TRANSFORMER' && provider.capability === 'EMBEDDING');
    const chat = current.find((provider) => provider.provider_type === 'OLLAMA' && provider.capability === 'CHAT' && provider.model === this.localChatModel);
    forkJoin({
      embedding: embedding ? of(embedding) : this.api.createProvider(this.selectedOrganization, {
        name: 'Embedding local', provider_type: 'LOCAL_SENTENCE_TRANSFORMER', capability: 'EMBEDDING',
        model: 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', dimension: 384,
      }),
      chat: chat ? of(chat) : this.api.createProvider(this.selectedOrganization, {
        name: 'Chat Ollama', provider_type: 'OLLAMA', capability: 'CHAT', model: this.localChatModel, base_url: 'http://ollama:11434',
      }),
    }).subscribe({
      next: ({ embedding: embeddingProvider, chat: chatProvider }) => this.api.bindWorkspaceProviders(this.selectedWorkspace, embeddingProvider.id, chatProvider.id).subscribe({
        next: () => { this.providers.update((items) => [...items.filter((item) => item.id !== embeddingProvider.id && item.id !== chatProvider.id), embeddingProvider, chatProvider]); this.error.set(''); },
        error: () => this.error.set('Không thể gắn provider vào workspace.'),
      }),
      error: () => this.error.set('Không thể cấu hình Ollama. Kiểm tra model và dịch vụ Ollama.'),
    });
  }

  protected configureGemini(): void {
    if (!this.selectedOrganization || !this.selectedWorkspace || !this.geminiApiKey.trim()) {
      this.error.set('Nhập Gemini API key trước khi lưu cấu hình Gemini.');
      return;
    }
    const baseUrl = 'https://generativelanguage.googleapis.com/v1beta/openai';
    const current = this.providers();
    const existingEmbedding = current.find((provider) =>
      provider.provider_type === 'GOOGLE_GEMINI' && provider.capability === 'EMBEDDING' && provider.model === 'gemini-embedding-2');
    const existingChat = current.find((provider) =>
      provider.provider_type === 'GOOGLE_GEMINI' && provider.capability === 'CHAT' && provider.model === this.geminiChatModel);
    forkJoin({
      embedding: existingEmbedding ? this.api.updateProvider(existingEmbedding.id, { secret: this.geminiApiKey }) : this.api.createProvider(this.selectedOrganization, {
        name: 'Embedding Gemini', provider_type: 'GOOGLE_GEMINI', capability: 'EMBEDDING',
        base_url: baseUrl, model: 'gemini-embedding-2', dimension: 3072, secret: this.geminiApiKey,
      }),
      chat: existingChat ? this.api.updateProvider(existingChat.id, { secret: this.geminiApiKey }) : this.api.createProvider(this.selectedOrganization, {
        name: 'Chat Gemini', provider_type: 'GOOGLE_GEMINI', capability: 'CHAT',
        base_url: baseUrl, model: this.geminiChatModel, secret: this.geminiApiKey,
      }),
    }).subscribe({
      next: ({ embedding, chat }) => this.api.bindWorkspaceProviders(this.selectedWorkspace, embedding.id, chat.id).subscribe({
        next: () => {
          this.geminiApiKey = '';
          this.providers.update((items) => [...items.filter((item) => item.id !== embedding.id && item.id !== chat.id), embedding, chat]);
          this.error.set('');
        },
        error: () => this.error.set('Không thể gắn Gemini vào workspace.'),
      }),
      error: () => this.error.set('Không thể lưu Gemini. Kiểm tra API key và model rồi thử lại.'),
    });
  }

  protected saveBot(): void {
    if (!this.selectedWorkspace || !this.botName.trim()) return;
    const current = this.selectedBot();
    const payload: ChatbotInput = { name: this.botName.trim(), system_prompt: this.botPrompt.trim(), retrieval_limit: Number(this.botRetrievalLimit), published: current?.published ?? false };
    const request = current ? this.api.updateChatbot(current.id, payload) : this.api.createChatbot(this.selectedWorkspace, payload);
    request.subscribe({
      next: (bot) => { this.bots.update((items) => current ? items.map((item) => item.id === bot.id ? bot : item) : [...items, bot]); this.selectBot(bot); },
      error: () => this.error.set('Không thể lưu chatbot. Hãy kiểm tra cấu hình AI.'),
    });
  }

  protected togglePublish(): void {
    const bot = this.selectedBot();
    if (!bot) return;
    this.api.updateChatbot(bot.id, { published: !bot.published }).subscribe({
      next: (saved) => { this.bots.update((items) => items.map((item) => item.id === saved.id ? saved : item)); this.selectBot(saved); },
      error: () => this.error.set('Không thể đổi trạng thái xuất bản chatbot.'),
    });
  }

  protected selectBot(bot: Chatbot | null): void {
    this.selectedBot.set(bot); this.messages.set([]); this.conversationId = null;
    if (bot) { this.botName = bot.name; this.botPrompt = bot.system_prompt; this.botRetrievalLimit = bot.retrieval_limit; }
  }

  protected send(): void {
    const bot = this.selectedBot();
    const question = this.chatInput.trim();
    if (!bot || !bot.published || !question || this.isStreaming()) return;
    this.chatInput = ''; this.isStreaming.set(true);
    this.messages.set([{ role: 'user', content: question }, { role: 'assistant', content: '' }]);
    void this.api.streamChat(bot.id, { message: question, conversation_id: this.conversationId }, (event) => this.handleStream(event));
  }

  protected citationLabel(citation: Citation): string { return `${citation.document_name ?? 'Tài liệu'}${citation.page_number ? ` · trang ${citation.page_number}` : ''}`; }
  protected selectCitation(citation: Citation): void {
    const document = citation.document_id
      ? this.documents().find((item) => item.id === citation.document_id)
      : this.documents().find((item) => item.name === citation.document_name);
    if (document) this.selectDocument(document.id);
  }

  private handleStream(event: ChatStreamEvent): void {
    if (event.event === 'conversation' && typeof event.data['conversation_id'] === 'string') this.conversationId = event.data['conversation_id'];
    if (event.event === 'token' && typeof event.data['text'] === 'string') this.updateAssistant((message) => ({ ...message, content: message.content + event.data['text'] }));
    if (event.event === 'citations' && Array.isArray(event.data['citations'])) this.updateAssistant((message) => ({ ...message, citations: event.data['citations'] as Citation[] }));
    if (event.event === 'error') this.error.set(typeof event.data['message'] === 'string' ? event.data['message'] : 'Chatbot gặp lỗi khi tạo câu trả lời.');
    if (event.event === 'done' || event.event === 'error') this.isStreaming.set(false);
  }

  private updateAssistant(update: (message: TranscriptMessage) => TranscriptMessage): void {
    this.messages.update((items) => items.map((message, index) => index === items.length - 1 ? update(message) : message));
  }

  private loadDocuments(): void {
    if (!this.selectedWorkspace) return;
    this.api.documents(this.selectedWorkspace).subscribe({
      next: (items) => this.documents.set(items),
      error: () => this.error.set('Không thể tải tài liệu của workspace.'),
    });
  }
}
