import { PasswordToggleDirective } from "../shared/password-toggle.directive";
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RaghubApiService, ProviderConfig, ProviderType, ProviderCapability } from '../core/raghub-api.service';
import { session } from '../core/api-auth.interceptor';

@Component({
  selector: 'raghub-ai-settings', imports: [PasswordToggleDirective,FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <main>
      <header><h1>Cấu hình AI</h1><p>Quản lý model dùng cho các workspace. Chọn provider trong cài đặt từng workspace.</p></header>
      @if (notice()) { <p role="status">{{ notice() }}</p> }
      @if (error()) { <p role="alert">{{ error() }}</p> }
      <section><h2>Thêm provider</h2>
        <form (ngSubmit)="save()">
          <label>Loại provider<select name="type" [(ngModel)]="type" (ngModelChange)="defaults()">
            <option value="LOCAL_SENTENCE_TRANSFORMER">Sentence Transformer (local)</option>
            <option value="OLLAMA">Ollama (local)</option>
            <option value="GOOGLE_GEMINI">Gemini</option>
            <option value="OPENAI_COMPATIBLE">OpenAI-compatible</option>
          </select></label>
          <label>Tên<input name="name" [(ngModel)]="name" required maxlength="200" /></label>
          <label>Chức năng<select name="capability" [(ngModel)]="capability"
            [disabled]="type === 'OLLAMA' || type === 'LOCAL_SENTENCE_TRANSFORMER'">
            <option value="EMBEDDING">Embedding</option><option value="CHAT">Chat</option>
          </select></label>
          <label>Model<input name="model" [(ngModel)]="model" required /></label>
          @if (capability === 'EMBEDDING') {
            <label>Số chiều<input name="dimension" type="number" min="1" max="65536" [(ngModel)]="dimension" required /></label>
          }
          @if (type !== 'LOCAL_SENTENCE_TRANSFORMER') {
            <label>Base URL<input name="baseUrl" type="url" [(ngModel)]="baseUrl" /></label>
          }
          @if (type === 'GOOGLE_GEMINI' || type === 'OPENAI_COMPATIBLE') {
            <label>API key<input name="secret" type="password" autocomplete="off" [(ngModel)]="secret" /></label>
          }
          <button type="submit" [disabled]="busy() || !name.trim() || !model.trim()">{{ busy() ? 'Đang lưu…' : 'Lưu provider' }}</button>
        </form>
      </section>
      <section><h2>Provider đã cấu hình</h2>
        @for (provider of providers(); track provider.id) {
          <article><div><h3>{{ provider.name }}</h3><p>{{ provider.model }} · {{ provider.capability }} · {{ provider.enabled ? 'Đang bật' : 'Đã tắt' }}</p></div>
            <button type="button" (click)="test(provider)" [disabled]="busy()">Kiểm tra kết nối</button>
            <button type="button" (click)="toggle(provider)" [disabled]="busy()">{{ provider.enabled ? 'Tắt' : 'Bật' }}</button>
          </article>
        } @empty { <p>Thêm Sentence Transformer và Ollama để bắt đầu dùng AI local.</p> }
      </section>
    </main>`,
  styles: `
    main { color:#173665; } section { background:#fff; padding:24px; border-radius:12px; margin:20px 0; }
    form { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; }
    label { display:flex; flex-direction:column; gap:8px; } input, select, button { min-height:44px; padding:10px; border:1px solid #d8e7f8; border-radius:8px; }
    button { cursor:pointer; color:#075fd8; background:#e8f3ff; } button:disabled { opacity:.6; cursor:wait; }
    article { display:flex; align-items:center; flex-wrap:wrap; gap:12px; border-bottom:1px solid #d8e7f8; padding:12px 0; } article div { flex:1 1 220px; }
    :is(input,select,button):focus-visible { outline:3px solid #0866ff; outline-offset:2px; }
  `,
})
export class AiSettingsComponent {
  protected readonly providers = signal<ProviderConfig[]>([]);
  protected readonly notice = signal('');
  protected readonly error = signal('');
  protected readonly busy = signal(false);
  protected type: ProviderType = 'LOCAL_SENTENCE_TRANSFORMER';
  protected capability: ProviderCapability = 'EMBEDDING';
  protected name = 'Embedding local';
  protected model = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2';
  protected dimension = 384;
  protected baseUrl = '';
  protected secret = '';
  private readonly api = inject(RaghubApiService);
  private organizationId = '';

  constructor() {
    this.api.organizations().subscribe({next: items => {
      this.organizationId = items.find(item => item.id === session.organizationId)?.id ?? items[0]?.id ?? '';
      session.organizationId = this.organizationId || null;
      this.load();
    }, error: () => this.error.set('Không thể tải cấu hình cài đặt.')});
  }
  protected defaults(): void {
    this.secret = '';
    this.name = this.type === 'OLLAMA' ? 'Chat Ollama' : 'Embedding local';
    this.capability = this.type === 'LOCAL_SENTENCE_TRANSFORMER' ? 'EMBEDDING' : 'CHAT';
    this.model = this.type === 'LOCAL_SENTENCE_TRANSFORMER' ? 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2' : this.type === 'OLLAMA' ? 'gemma3:1b' : '';
    this.baseUrl = this.type === 'OLLAMA' ? 'http://ollama:11434' : '';
  }
  protected save(): void {
    if (!this.organizationId || this.busy()) return;
    this.busy.set(true); this.error.set('');
    this.api.createProvider(this.organizationId, {
      name: this.name.trim(), provider_type: this.type, capability: this.capability,
      model: this.model.trim(), ...(this.capability === 'EMBEDDING' ? {dimension: this.dimension} : {}),
      ...(this.baseUrl.trim() ? {base_url: this.baseUrl.trim()} : {}),
      ...(this.secret ? {secret: this.secret} : {}),
    }).subscribe({next: () => {
      this.secret = ''; this.busy.set(false); this.notice.set('Đã lưu provider.'); this.load();
    }, error: () => {this.busy.set(false); this.error.set('Không thể lưu. Kiểm tra model, URL và số chiều.');}});
  }
  protected test(provider: ProviderConfig): void {
    this.busy.set(true); this.error.set(''); this.notice.set('Đang kiểm tra model…');
    this.api.testProvider(provider.id).subscribe({next: result => {
      this.busy.set(false);
      const check = result as {status?: string};
      this.notice.set(check.status?.toLowerCase() === 'ok' ? `${provider.name}: kết nối thành công.` : 'Kiểm tra thất bại.');
    }, error: () => {this.busy.set(false); this.error.set('Không thể kết nối provider.');}});
  }
  protected toggle(provider: ProviderConfig): void {
    this.busy.set(true);
    this.api.updateProvider(provider.id, {enabled: !provider.enabled}).subscribe({
      next: () => {this.busy.set(false); this.load();},
      error: () => {this.busy.set(false); this.error.set('Không thể cập nhật provider.');},
    });
  }
  private load(): void {
    if (this.organizationId) this.api.providers(this.organizationId).subscribe({
      next: items => this.providers.set(items), error: () => this.error.set('Không thể tải provider.'),
    });
  }
}
