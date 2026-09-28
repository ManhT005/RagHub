import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { forkJoin, of } from 'rxjs';

import { session } from '../core/api-auth.interceptor';
import {
  Chatbot, ChatbotInput, ChatStreamEvent, Organization, ProviderConfig,
  RaghubApiService, Workspace,
} from '../core/raghub-api.service';

interface Citation {
  document_name?: string;
  page_number?: number | null;
  excerpt?: string;
  rank?: number;
}

interface TranscriptMessage {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
}

@Component({
  selector: 'raghub-chatbots',
  imports: [FormsModule, RouterLink],
  templateUrl: './chatbots.component.html',
  styleUrl: './chatbots.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChatbotsComponent {
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly providers = signal<ProviderConfig[]>([]);
  protected readonly bots = signal<Chatbot[]>([]);
  protected readonly selectedBot = signal<Chatbot | null>(null);
  protected readonly messages = signal<TranscriptMessage[]>([]);
  protected readonly error = signal('');
  protected readonly notice = signal('');
  protected readonly isStreaming = signal(false);

  protected selectedOrganization = session.organizationId ?? '';
  protected selectedWorkspace = '';
  protected selectedEmbeddingProvider = '';
  protected selectedChatProvider = '';
  protected localChatModel = 'gemma3:4b';
  protected readonly localEmbeddingModel = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2';
  protected geminiApiKey = '';
  protected geminiChatModel = 'gemini-2.5-flash';
  protected botName = 'Trợ lý tài liệu';
  protected botPrompt = 'Trả lời bằng tiếng Việt, chỉ dựa trên tài liệu đã tải lên. Nếu không đủ thông tin, hãy nói rõ điều đó.';
  protected botRetrievalLimit = 5;
  protected chatInput = '';
  private conversationId: string | null = null;
  private readonly api = inject(RaghubApiService);

  constructor() { this.loadOrganizations(); }

  protected loadOrganizations(): void {
    this.api.organizations().subscribe({
      next: (items) => {
        this.organizations.set(items);
        if (!this.selectedOrganization && items[0]) this.selectedOrganization = items[0].id;
        this.changeOrganization();
      },
      error: () => this.setError('Hãy đăng nhập và chọn tổ chức trước khi cấu hình chatbot.'),
    });
  }

  protected changeOrganization(): void {
    session.organizationId = this.selectedOrganization || null;
    this.resetWorkspaceState();
    if (!this.selectedOrganization) return;
    this.api.workspaces().subscribe({
      next: (items) => {
        this.workspaces.set(items);
        this.selectedWorkspace = items[0]?.id ?? '';
        this.changeWorkspace();
      },
      error: () => this.setError('Không thể tải không gian làm việc của tổ chức này.'),
    });
  }

  protected changeWorkspace(): void {
    this.providers.set([]);
    this.bots.set([]);
    this.selectedBot.set(null);
    this.messages.set([]);
    this.conversationId = null;
    if (!this.selectedWorkspace || !this.selectedOrganization) return;
    this.api.providers(this.selectedOrganization).subscribe({
      next: (items) => this.providers.set(items),
      error: () => this.setError('Không thể tải danh sách nhà cung cấp AI.'),
    });
    this.api.chatbots(this.selectedWorkspace).subscribe({
      next: (items) => {
        this.bots.set(items);
        const published = items.find((bot) => bot.published) ?? items[0] ?? null;
        this.selectBot(published);
      },
      error: () => this.setError('Không thể tải chatbot của không gian làm việc.'),
    });
  }

  protected configureLocal(): void {
    if (!this.selectedOrganization || !this.selectedWorkspace) return;
    this.clearMessages();
    const current = this.providers();
    const embedding = current.find((provider) =>
      provider.provider_type === 'LOCAL_SENTENCE_TRANSFORMER' && provider.capability === 'EMBEDDING' && provider.model === this.localEmbeddingModel);
    const chat = current.find((provider) =>
      provider.provider_type === 'OLLAMA' && provider.capability === 'CHAT' && provider.model === this.localChatModel);
    forkJoin({
      embedding: embedding ? of(embedding) : this.api.createProvider(this.selectedOrganization, {
        name: 'Embedding local', provider_type: 'LOCAL_SENTENCE_TRANSFORMER', capability: 'EMBEDDING',
        model: this.localEmbeddingModel, dimension: 384,
      }),
      chat: chat ? of(chat) : this.api.createProvider(this.selectedOrganization, {
        name: 'Chat Ollama', provider_type: 'OLLAMA', capability: 'CHAT', model: this.localChatModel,
        base_url: 'http://ollama:11434',
      }),
    }).subscribe({
      next: ({ embedding: embeddingProvider, chat: chatProvider }) => {
        this.selectedEmbeddingProvider = embeddingProvider.id;
        this.selectedChatProvider = chatProvider.id;
        this.bindProviders();
      },
      error: () => this.setError('Không thể tạo provider local. Kiểm tra Ollama, model và nhật ký API.'),
    });
  }

  protected configureGemini(): void {
    if (!this.selectedOrganization || !this.selectedWorkspace || !this.geminiApiKey.trim()) {
      this.setError('Nhập Gemini API key trước khi cấu hình Gemini.');
      return;
    }
    this.clearMessages();
    const baseUrl = 'https://generativelanguage.googleapis.com/v1beta/openai';
    forkJoin({
      embedding: this.api.createProvider(this.selectedOrganization, {
        name: 'Embedding Gemini', provider_type: 'GOOGLE_GEMINI', capability: 'EMBEDDING',
        base_url: baseUrl, model: 'gemini-embedding-001', dimension: 3072, secret: this.geminiApiKey,
      }),
      chat: this.api.createProvider(this.selectedOrganization, {
        name: 'Chat Gemini', provider_type: 'GOOGLE_GEMINI', capability: 'CHAT',
        base_url: baseUrl, model: this.geminiChatModel, secret: this.geminiApiKey,
      }),
    }).subscribe({
      next: ({ embedding, chat }) => {
        this.geminiApiKey = '';
        this.selectedEmbeddingProvider = embedding.id;
        this.selectedChatProvider = chat.id;
        this.bindProviders();
      },
      error: () => this.setError('Không thể lưu Gemini. Kiểm tra API key và model rồi thử lại.'),
    });
  }

  protected bindProviders(): void {
    if (!this.selectedWorkspace || !this.selectedEmbeddingProvider || !this.selectedChatProvider) {
      this.setError('Chọn cả embedding và chat provider trước khi lưu.');
      return;
    }
    this.api.bindWorkspaceProviders(this.selectedWorkspace, this.selectedEmbeddingProvider, this.selectedChatProvider).subscribe({
      next: () => {
        this.notice.set('Provider đã được gắn vào workspace. Tài liệu READY có thể dùng để hỏi đáp.');
        this.error.set('');
        this.reloadProviders();
      },
      error: () => this.setError('Không thể gắn provider vào workspace. Hãy kiểm tra quyền và provider đã tạo.'),
    });
  }

  protected testProvider(provider: ProviderConfig): void {
    this.clearMessages();
    this.api.testProvider(provider.id).subscribe({
      next: () => this.notice.set(`Kết nối ${provider.name} hoạt động.`),
      error: () => this.setError(`Không thể kết nối ${provider.name}. Kiểm tra model, API key hoặc Ollama.`),
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
        this.notice.set('Chatbot đã được tạo. Hãy xuất bản để thử chat.');
      },
      error: () => this.setError('Không thể tạo chatbot. Hãy cấu hình provider trước và kiểm tra quyền workspace.'),
    });
  }

  protected saveBot(): void {
    const bot = this.selectedBot();
    if (!bot) return this.createBot();
    this.clearMessages();
    this.api.updateChatbot(bot.id, this.botPayload(bot.published)).subscribe({
      next: (saved) => this.replaceBot(saved),
      error: () => this.setError('Không thể lưu thay đổi chatbot.'),
    });
  }

  protected togglePublish(): void {
    const bot = this.selectedBot();
    if (!bot) return;
    this.clearMessages();
    this.api.updateChatbot(bot.id, { published: !bot.published }).subscribe({
      next: (saved) => {
        this.replaceBot(saved);
        this.notice.set(saved.published ? 'Chatbot đã được xuất bản.' : 'Chatbot đã chuyển về bản nháp.');
      },
      error: () => this.setError('Không thể đổi trạng thái xuất bản.'),
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
    if (!bot || !bot.published || !question || this.isStreaming()) return;
    this.clearMessages();
    this.chatInput = '';
    this.isStreaming.set(true);
    this.messages.set([{ role: 'user', content: question }, { role: 'assistant', content: '' }]);
    void this.api.streamChat(bot.id, { message: question, conversation_id: this.conversationId }, (event) => this.handleStream(event));
  }

  protected citationLabel(citation: Citation): string {
    return `${citation.document_name ?? 'Tài liệu'}${citation.page_number ? ` · trang ${citation.page_number}` : ''}`;
  }

  private handleStream(event: ChatStreamEvent): void {
    if (event.event === 'conversation' && typeof event.data['conversation_id'] === 'string') this.conversationId = event.data['conversation_id'];
    if (event.event === 'token' && typeof event.data['text'] === 'string') this.updateAssistant((message) => ({ ...message, content: message.content + event.data['text'] }));
    if (event.event === 'citations' && Array.isArray(event.data['citations'])) this.updateAssistant((message) => ({ ...message, citations: event.data['citations'] as Citation[] }));
    if (event.event === 'error') this.setError(typeof event.data['message'] === 'string' ? event.data['message'] : 'Chatbot gặp lỗi khi tạo câu trả lời.');
    if (event.event === 'done' || event.event === 'error') this.isStreaming.set(false);
  }

  private updateAssistant(update: (message: TranscriptMessage) => TranscriptMessage): void {
    this.messages.update((items) => items.map((message, index) => index === items.length - 1 ? update(message) : message));
  }

  private botPayload(published: boolean): ChatbotInput {
    return {
      name: this.botName.trim(), system_prompt: this.botPrompt.trim(),
      retrieval_limit: Number(this.botRetrievalLimit), published,
    };
  }

  private replaceBot(saved: Chatbot): void {
    this.bots.update((items) => items.map((item) => item.id === saved.id ? saved : item));
    this.selectedBot.set(saved);
    this.notice.set('Đã lưu chatbot.');
    this.error.set('');
  }

  private reloadProviders(): void {
    if (!this.selectedOrganization) return;
    this.api.providers(this.selectedOrganization).subscribe({ next: (items) => this.providers.set(items) });
  }

  private resetWorkspaceState(): void {
    this.workspaces.set([]); this.providers.set([]); this.bots.set([]); this.selectedWorkspace = '';
    this.selectedBot.set(null); this.messages.set([]); this.conversationId = null;
  }

  private clearMessages(): void { this.error.set(''); this.notice.set(''); }
  private setError(message: string): void { this.error.set(message); this.notice.set(''); }
}
