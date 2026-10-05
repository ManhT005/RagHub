import { ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { NzButtonModule } from 'ng-zorro-antd/button';
import { NzAlertModule } from 'ng-zorro-antd/alert';
import { Subscription, finalize, forkJoin } from 'rxjs';
import { ProviderApiService, RegistryModel, selectableModel } from '../../core/api/provider-api.service';
import { WorkspaceContextStore } from '../../core/workspace-context/workspace-context.store';
import { apiError } from '../../core/api/api-error';

@Component({
  selector: 'raghub-rerank-profile',
  imports: [FormsModule, NzButtonModule, NzAlertModule],
  template: `<section class="surface" style="margin-top:24px">
    <h2>Rerank model <small class="muted">Tùy chọn</small></h2>
    <p>Sắp xếp lại các kết quả tìm kiếm trước khi tạo câu trả lời. Nếu model gặp lỗi,
      hệ thống sử dụng thứ tự tìm kiếm ban đầu.</p>
    @if (loading()) { <p role="status">Đang tải cấu hình rerank…</p> }
    @if (context.can('workspace.edit')) {
      <fieldset [disabled]="busy() || loading()">
        <label>Model<select [(ngModel)]="selected">
          <option value="">Tắt rerank</option>
          @if (unavailable()) { <option [value]="selected" disabled>Model đã gắn hiện không khả dụng</option> }
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
  constructor() {
    const workspaceId = computed(() => this.context.workspace()?.id);
    effect(() => {
      const id = workspaceId();
      this.request?.unsubscribe();
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
        this.selected = binding.model_id ?? '';
        this.candidateLimit = binding.candidate_limit;
        this.topN = binding.top_n;
        this.timeoutSeconds = binding.timeout_seconds;
      }, error: error => this.error.set(apiError(error)) });
  }
  protected unavailable() { return !!this.selected && !this.models().some(model => model.id === this.selected); }
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
    this.api.bindRerank(id, { model_id: this.selected || null, candidate_limit: this.candidateLimit,
      top_n: this.topN, timeout_seconds: this.timeoutSeconds })
      .pipe(finalize(() => this.busy.set(false)), takeUntilDestroyed(this.destroyRef))
      .subscribe({ next: () => this.notice.set('Đã cập nhật rerank.'), error: error => this.error.set(apiError(error)) });
  }
}
