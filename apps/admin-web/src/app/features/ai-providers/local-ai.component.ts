import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { NzButtonModule } from 'ng-zorro-antd/button';
import { NzAlertModule } from 'ng-zorro-antd/alert';
import { Subscription, exhaustMap, finalize, timer } from 'rxjs';
import { LocalAiModel, ProviderApiService } from '../../core/api/provider-api.service';
import { RaghubApiService } from '../../core/raghub-api.service';
import { consoleOrganization } from '../../core/console-organization';
import { session } from '../../core/api-auth.interceptor';
import { apiError } from '../../core/api/api-error';

@Component({
  selector: 'raghub-local-ai',
  imports: [RouterLink, NzButtonModule, NzAlertModule],
  template: `<main class="selfhost-page">
    <header class="page-heading"><div><p class="eyebrow">AI & Models / System</p><h1>Local AI</h1>
      <p>Xem và tải model embedding về máy chủ RagHub.</p></div>
      <a nz-button routerLink="/system/ai/providers">AI Providers →</a></header>
    <p class="muted">Model đã tải chưa tự động được gắn vào workspace. Ollama được quản lý trong AI Providers.</p>
    @if (error()) { <nz-alert nzType="error" [nzMessage]="error()" nzShowIcon /> }
    @if (loading()) { <p role="status">Đang tải danh sách model…</p> }
    <div class="provider-grid">
      @for (model of models(); track model.id) {
        <article class="surface provider-card">
          <h2>{{ model.repo.split('/').pop() }}</h2>
          <p>{{ model.languages }} · {{ model.dimension }} dimensions · ~{{ megabytes(model.approximate_bytes) }} MB</p>
          <p role="status">{{ statusLabel(model.status) }}</p>
          @if (active(model)) {
            <progress [value]="model.completed_bytes" [max]="model.total_bytes || 1"
              [attr.aria-label]="'Tiến độ tải ' + model.repo"></progress>
            <p>{{ megabytes(model.completed_bytes) }} / {{ megabytes(model.total_bytes) }} MB</p>
          }
          @if (model.error_code) { <p class="muted">{{ model.error_code }}</p> }
          <div class="card-actions"><a [href]="model.docs_url" target="_blank" rel="noopener noreferrer">Thông tin model ↗</a>
            <button nz-button nzType="primary" [nzLoading]="busy() === model.id"
              [disabled]="anyActive() || !!busy() || model.status === 'INSTALLED'" (click)="download(model)">
              {{ model.status === 'INSTALLED' ? 'Đã tải' : model.status === 'FAILED' ? 'Thử tải lại' : 'Tải model' }}
            </button></div>
        </article>
      }
    </div>
  </main>`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LocalAiComponent {
  protected readonly models = signal<LocalAiModel[]>([]);
  protected readonly error = signal('');
  protected readonly loading = signal(true);
  protected readonly busy = signal('');
  private readonly providers = inject(ProviderApiService);
  private readonly auth = inject(RaghubApiService);
  private readonly destroyRef = inject(DestroyRef);
  private org = '';
  private polling?: Subscription;
  constructor() {
    this.auth.organizations().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: items => {
      this.org = consoleOrganization(items)?.id ?? '';
      session.organizationId = this.org || null;
      if (this.org) this.poll(); else this.loading.set(false);
    }, error: error => { this.loading.set(false); this.error.set(apiError(error)); } });
  }
  protected megabytes(value: number) { return Math.round(value / 1_000_000); }
  protected active(model: LocalAiModel) { return ['QUEUED', 'DOWNLOADING', 'VERIFYING'].includes(model.status); }
  protected anyActive() { return this.models().some(model => this.active(model)); }
  protected statusLabel(status: string) {
    return ({ AVAILABLE: 'Có thể tải', QUEUED: 'Đang chờ', DOWNLOADING: 'Đang tải',
      VERIFYING: 'Đang kiểm tra', INSTALLED: 'Đã tải xuống', FAILED: 'Tải thất bại' } as Record<string, string>)[status] || status;
  }
  private poll() {
    this.polling?.unsubscribe();
    this.polling = timer(0, 2000).pipe(exhaustMap(() => this.providers.localModels(this.org)), takeUntilDestroyed(this.destroyRef))
      .subscribe({ next: models => {
        this.models.set(models); this.loading.set(false);
        if (!this.anyActive()) this.polling?.unsubscribe();
      }, error: error => { this.error.set(apiError(error)); this.loading.set(false); } });
  }
  protected download(model: LocalAiModel) {
    if (!this.org || this.anyActive() || this.busy() || model.status === 'INSTALLED') return;
    this.busy.set(model.id); this.error.set('');
    this.providers.downloadLocal(this.org, model.id)
      .pipe(finalize(() => this.busy.set('')), takeUntilDestroyed(this.destroyRef))
      .subscribe({ next: () => this.poll(), error: error => this.error.set(apiError(error)) });
  }
}
