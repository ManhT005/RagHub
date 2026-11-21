import { ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { NzButtonModule } from 'ng-zorro-antd/button';
import { NzAlertModule } from 'ng-zorro-antd/alert';
import { Subscription, exhaustMap, finalize, forkJoin, timer } from 'rxjs';
import { LocalRerankStatus, ProviderApiService, RegistryModel, selectableModel } from '../../core/api/provider-api.service';
import { WorkspaceContextStore } from '../../core/workspace-context/workspace-context.store';
import { apiError } from '../../core/api/api-error';

@Component({
  selector: 'raghub-rerank-profile',
  imports: [FormsModule, NzButtonModule, NzAlertModule],
  template: `<section class="surface" style="margin-top:24px">
    <h2>Reranking <small class="muted">Tùy chọn</small></h2>
    <p>Sắp xếp lại các kết quả tìm kiếm trước khi tạo câu trả lời. Nếu model gặp lỗi,
      hệ thống sử dụng thứ tự tìm kiếm ban đầu.</p>
    @if (loading()) { <p role="status">Đang tải cấu hình rerank…</p> }
    @if (localModels().length > 1) {
      <label>Model reranking local<select [(ngModel)]="localModelId" (ngModelChange)="localModelChanged()" [disabled]="busy() || loading()">
        @for (model of localModels(); track model.catalog_id) {
          <option [value]="model.catalog_id">{{ model.model }}</option>
        }
      </select></label>
      @if (localModelId === 'qwen3-reranker-06b') {
        <p class="muted">Qwen3 tải khoảng 1,2 GB. Trên CPU nên bắt đầu với 5 ứng viên, thời gian chờ 30 giây. Lần nạp model đầu tiên có thể lâu hơn.</p>
      }
    }
    @if (activeLocal(); as runtime) {
      <p role="status"><strong>Reranking local trên VPS:</strong> {{ localStatus() }}</p>
      <p class="muted">{{ runtime.model }} · CPU · Không cần API key hay lập chỉ mục lại.</p>
      @if (!runtime.ready && runtime.can_prepare && context.can('workspace.edit')) {
        <button nz-button [nzLoading]="preparing() || downloading()"
          [disabled]="preparing() || downloading() || !runtime.download_enabled"
          (click)="prepareLocal()">{{ runtime.status === 'FAILED' ? 'Thử tải lại model local' : 'Tải model local' }}</button>
      } @else if (!runtime.ready && !runtime.can_prepare) {
        <p>Nhờ quản trị viên tải model local để sử dụng.</p>
      }
    }
    @if (context.can('workspace.edit')) {
      <fieldset [disabled]="busy() || loading()">
        <label>Chế độ reranking<select [(ngModel)]="selected" (ngModelChange)="selectionChanged()">
          <option value="">Tắt reranking</option>
          <option value="__local__" [disabled]="!activeLocal()?.ready">Reranking local trên VPS</option>
          @if (selected !== '__local__' && unavailable()) { <option [value]="selected" disabled>Model đã gắn hiện không khả dụng</option> }
          @for (model of models(); track model.id) {
            <option [value]="model.id">{{ model.display_name || model.model }} · {{ model.provider_name }}</option>
          }
        </select></label>
        @if (selected) {
          <label>Số kết quả đầu vào<input type="number" min="1" max="200" [(ngModel)]="candidateLimit" /></label>
          <label>Số kết quả giữ lại<input type="number" min="1" [max]="candidateLimit" [(ngModel)]="topN" /></label>
          <label>Thời gian chờ tối đa (giây)<input type="number" min="0.1" max="30" step="0.1" [(ngModel)]="timeoutSeconds" /></label>
        }
        <button nz-button nzType="primary" [nzLoading]="busy()" [disabled]="!valid() || unavailable()" (click)="save()">Lưu rerank</button>
      </fieldset>
    } @else { <p>{{ selected ? 'Workspace đã cấu hình rerank.' : 'Rerank đang tắt.' }}</p> }
    @if (error()) { <nz-alert nzType="error" [nzMessage]="error()" nzShowIcon /> }
    @if (notice()) { <p role="status">{{ notice() }}</p> }
  </section>`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RerankProfileComponent {
  protected readonly context = inject(WorkspaceContextStore);
  protected readonly models = signal<RegistryModel[]>([]);
  protected readonly local = signal<LocalRerankStatus | null>(null);
  protected readonly localModels = signal<LocalRerankStatus[]>([]);
  protected localModelId = 'mmarco-minilm-reranker';
  protected activeLocal() {
    return this.localModels().find(model => model.catalog_id === this.localModelId)
      ?? (this.localModelId === 'mmarco-minilm-reranker' ? this.local() : null);
  }
  protected localModelChanged() {
    this.notice.set(''); this.error.set('');
    if (this.selected === '__local__' && this.localModelId === 'qwen3-reranker-06b') {
      this.candidateLimit = 5; this.topN = Math.min(this.topN, 5); this.timeoutSeconds = 30;
    }
  }
  protected readonly preparing = signal(false);
  protected readonly busy = signal(false);
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly notice = signal('');
  protected selected = '';
  protected candidateLimit = 40;
  protected topN = 8;
  protected timeoutSeconds = 5;
  private readonly api = inject(ProviderApiService);
  private readonly destroyRef = inject(DestroyRef);
  private request?: Subscription;
  private polling?: Subscription;
  constructor() {
    const workspaceId = computed(() => this.context.workspace()?.id);
    effect(() => {
      const id = workspaceId();
      this.request?.unsubscribe();
      this.polling?.unsubscribe();
      this.local.set(null);
      this.localModels.set([]);
      this.localModelId = 'mmarco-minilm-reranker';
      this.models.set([]);
      this.selected = '';
      this.error.set('');
      this.notice.set('');
      if (id) untracked(() => this.load(id));
    });
  }
  private load(id: string) {
    this.loading.set(true);
    this.request = forkJoin({ models: this.api.workspaceModels(id, 'RERANK'), binding: this.api.rerankBinding(id) })
      .pipe(finalize(() => this.loading.set(false)), takeUntilDestroyed(this.destroyRef))
      .subscribe({ next: ({ models, binding }) => {
        this.models.set(models.filter(selectableModel));
        this.local.set(binding.local ?? null);
        this.localModels.set(binding.local_models ?? []);
        this.localModelId = binding.local_model_id ?? 'mmarco-minilm-reranker';
        this.selected = binding.mode === 'local' ? '__local__' : binding.mode === 'off' ? '' : binding.model_id ?? '';
        this.candidateLimit = binding.candidate_limit;
        this.topN = binding.top_n;
        this.timeoutSeconds = binding.timeout_seconds;
        if (this.downloading()) this.poll(id);
      }, error: error => this.error.set(apiError(error)) });
  }
  protected downloading() { return ['QUEUED', 'DOWNLOADING', 'VERIFYING'].includes(this.activeLocal()?.status ?? ''); }
  protected localStatus() {
    return ({ AVAILABLE: 'Chưa tải model', QUEUED: 'Đang chờ tải', DOWNLOADING: 'Đang tải model…',
      VERIFYING: 'Đang xác minh model…', INSTALLED: 'Sẵn sàng', FAILED: 'Tải hoặc xác minh model thất bại',
      UNSUPPORTED: 'Máy chủ chưa có thư viện Local AI', DISABLED: 'Quản trị viên đã tắt reranking trên máy chủ',
    } as Record<string, string>)[this.activeLocal()?.status ?? ''] ?? 'Chưa sẵn sàng';
  }
  protected selectionChanged() {
    this.notice.set('');
    if (this.selected === '__local__') {
      this.candidateLimit = this.localModelId === 'qwen3-reranker-06b' ? 5 : 30;
      this.topN = 5; this.timeoutSeconds = this.localModelId === 'qwen3-reranker-06b' ? 30 : 20;
    }
  }
  protected prepareLocal() {
    const id = this.context.workspace()?.id;
    if (!id || !this.context.can('workspace.edit') || !this.activeLocal()?.can_prepare
      || !this.activeLocal()?.download_enabled || this.preparing() || this.downloading()) return;
    this.preparing.set(true); this.error.set('');
    const download = this.localModelId === 'mmarco-minilm-reranker'
      ? this.api.prepareLocalRerank(id) : this.api.prepareLocalRerank(id, this.localModelId);
    download.pipe(finalize(() => this.preparing.set(false)), takeUntilDestroyed(this.destroyRef))
      .subscribe({ next: () => { if (id === this.context.workspace()?.id) this.poll(id); }, error: error => this.error.set(apiError(error)) });
  }
  private poll(id: string) {
    this.polling?.unsubscribe();
    this.polling = timer(0, 2000).pipe(exhaustMap(() => this.api.rerankBinding(id)), takeUntilDestroyed(this.destroyRef))
      .subscribe({ next: binding => {
        this.local.set(binding.local ?? null);
        this.localModels.set(binding.local_models ?? []);
        if (!this.downloading()) this.polling?.unsubscribe();
      }, error: error => { this.error.set(apiError(error)); this.polling?.unsubscribe(); } });
  }
  protected unavailable() {
    if (this.selected === '__local__') return !this.activeLocal()?.ready;
    return !!this.selected && !this.models().some(model => model.id === this.selected);
  }
  protected valid() {
    return Number.isInteger(this.candidateLimit) && this.candidateLimit >= 1 && this.candidateLimit <= 200
      && Number.isInteger(this.topN) && this.topN >= 1 && this.topN <= Math.min(100, this.candidateLimit)
      && Number.isFinite(this.timeoutSeconds) && this.timeoutSeconds >= .1 && this.timeoutSeconds <= 30;
  }
  protected save() {
    const id = this.context.workspace()?.id;
    if (!id || !this.context.can('workspace.edit') || this.busy() || !this.valid() || this.unavailable()) return;
    this.busy.set(true);
    this.error.set('');
    this.notice.set('');
    const mode = this.selected === '__local__' ? 'local' : this.selected ? 'provider' : 'off';
    this.api.bindRerank(id, { mode, ...(mode === 'local' ? { local_model_id: this.localModelId } : {}), model_id: mode === 'provider' ? this.selected : null, candidate_limit: this.candidateLimit,
      top_n: this.topN, timeout_seconds: this.timeoutSeconds })
      .pipe(finalize(() => this.busy.set(false)), takeUntilDestroyed(this.destroyRef))
      .subscribe({ next: () => this.notice.set('Đã cập nhật rerank.'), error: error => this.error.set(apiError(error)) });
  }
}
