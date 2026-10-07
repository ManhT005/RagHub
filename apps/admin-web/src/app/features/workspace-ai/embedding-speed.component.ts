import { ChangeDetectionStrategy, Component, DestroyRef, effect, inject, signal, untracked } from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { FormsModule } from "@angular/forms";
import { Subscription, finalize } from "rxjs";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzButtonModule } from "ng-zorro-antd/button";
import { WorkspaceApiService, EmbeddingRuntimePolicy, EmbeddingExecutionPreference } from "../../core/api/workspace-api.service";
import { WorkspaceContextStore } from "../../core/workspace-context/workspace-context.store";
import { apiError } from "../../core/api/api-error";

@Component({
  selector: "raghub-embedding-speed",
  imports: [FormsModule, NzButtonModule, NzAlertModule],
  template: `<section class="surface" style="margin-top:24px">
    <h2>Tốc độ embedding</h2>
    <p class="muted">Điều chỉnh số request embedding chạy đồng thời và kích thước batch. Mức cao có thể nhanh hơn với API có quota lớn nhưng dễ chạm rate limit hơn.</p>
    @if (runtime(); as policy) {
      <p aria-live="polite">Giới hạn hiệu lực: {{ policy.effective_max_inflight }} request đồng thời · {{ policy.effective_batch_chunks }} chunks / batch · {{ policy.effective_batch_tokens }} tokens / batch.
      @if (policy.limited_by !== 'none') { <span>Được giới hạn bởi {{ limitLabel(policy.limited_by) }}.</span> }</p>
      @if (context.can('ai.change_embedding')) {
        <form #form="ngForm" (ngSubmit)="form.valid && save()">
          <label for="embedding-speed-profile">Mức tốc độ</label>
          <select id="embedding-speed-profile" name="profile" [(ngModel)]="preference.profile" [disabled]="busy()">
            <option [ngValue]="null">Theo mặc định provider / host</option>
            <option value="conservative">Tiết kiệm</option><option value="balanced">Cân bằng</option>
            <option value="fast">Nhanh</option><option value="custom">Tùy chỉnh</option>
          </select>
          @if (preference.profile === 'custom') {
            <div class="custom-settings">
              <label>Request đồng thời <input name="inflight" type="number" min="1" [max]="policy.max_allowed_inflight" [(ngModel)]="preference.max_inflight_requests" [disabled]="busy()" /></label>
              <label>Chunks / batch <input name="chunks" type="number" min="1" [max]="policy.max_allowed_batch_chunks" [(ngModel)]="preference.batch_max_chunks" [disabled]="busy()" /></label>
              <label>Tokens / batch <input name="tokens" type="number" min="1000" [max]="policy.max_allowed_batch_tokens" [(ngModel)]="preference.batch_target_tokens" [disabled]="busy()" /></label>
              <label>Số lần thử tối đa <input name="retries" type="number" min="1" max="48" [(ngModel)]="preference.retry_max_attempts" [disabled]="busy()" /></label>
              <label>Thời gian chờ mặc định (giây) <input name="delay" type="number" min="2" max="120" [(ngModel)]="preference.retry_delay_seconds" [disabled]="busy()" /></label>
            </div>
          }
          @if (form.invalid) { <p role="alert">Nhập giá trị trong giới hạn host/provider hiển thị.</p> }
          <button nz-button nzType="primary" type="submit" [disabled]="form.invalid" [nzLoading]="busy()">Lưu tốc độ embedding</button>
        </form>
      }
    }
    <p class="muted">Chi phí API thường phụ thuộc lượng dữ liệu hoặc tokens được embed. Burst cao hơn có thể chạm rate limit và tạo thêm retry. Local embedding dùng giới hạn riêng; thay đổi tốc độ áp dụng cho tài liệu mới và không yêu cầu reindex.</p>
    @if (error()) { <nz-alert nzType="error" [nzMessage]="error()" nzShowIcon /> }
    @if (notice()) { <p role="status">{{ notice() }}</p> }
  </section>`,
  styles: [`form{display:grid;gap:12px}select,input{min-height:40px;padding:8px;border:1px solid var(--border-color,#d9d9d9);border-radius:6px}label{display:grid;gap:6px}.custom-settings{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}button{justify-self:start}`],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EmbeddingSpeedComponent {
  protected readonly context = inject(WorkspaceContextStore);
  protected readonly runtime = signal<EmbeddingRuntimePolicy | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal("");
  protected readonly notice = signal("");
  protected preference: EmbeddingExecutionPreference = { profile: null };
  private readonly api = inject(WorkspaceApiService);
  private readonly destroyRef = inject(DestroyRef);
  private request?: Subscription;
  constructor() {
    effect(() => {
      const id = this.context.workspace()?.id;
      this.request?.unsubscribe();
      this.runtime.set(null); this.error.set(""); this.notice.set("");
      if (id) untracked(() => {
        this.request = this.api.embeddingRuntime(id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
          next: runtime => { this.runtime.set(runtime); this.preference = { profile: null, ...runtime.preference }; },
          error: error => this.error.set(apiError(error)),
        });
      });
    });
  }
  protected limitLabel(value: string) { return ({ host: "host", provider: "provider", local: "tài nguyên local" } as Record<string, string>)[value] ?? value; }
  protected save() {
    const id = this.context.workspace()?.id;
    if (!id || this.busy() || !this.context.can("ai.change_embedding")) return;
    this.busy.set(true); this.error.set(""); this.notice.set("");
    const preference: EmbeddingExecutionPreference = this.preference.profile === "custom"
      ? this.preference : { profile: this.preference.profile };
    this.request = this.api.changeEmbeddingRuntime(id, preference).pipe(
      finalize(() => this.busy.set(false)), takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: runtime => { this.runtime.set(runtime); this.notice.set("Đã lưu tốc độ embedding."); },
      error: error => this.error.set(apiError(error)),
    });
  }
}
