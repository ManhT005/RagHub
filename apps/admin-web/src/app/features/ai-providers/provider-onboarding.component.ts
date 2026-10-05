import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { FormsModule } from "@angular/forms";
import { NzDrawerModule } from "ng-zorro-antd/drawer";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzTagModule } from "ng-zorro-antd/tag";
import { from, concatMap, finalize, of, switchMap, forkJoin, timer, exhaustMap, takeWhile, Subscription } from "rxjs";
import {
  ProviderApiService,
  ProviderCatalogItem,
  ProviderConnection,
  DiscoveredModel,
  OllamaRecommendation,
  OllamaPullJob,
} from "../../core/api/provider-api.service";
import { ProviderCapability } from "../../core/raghub-api.service";
import { apiError } from "../../core/api/api-error";
import { resolveLegacyCatalogId } from '../../core/api/provider-catalog-identity';
import { ProviderLogoComponent } from '../../shared/provider-logo/provider-logo.component';

interface Choice extends DiscoveredModel {
  selected: boolean;
  registered: boolean;
  capability: ProviderCapability | "UNKNOWN";
}
@Component({
  selector: "raghub-provider-onboarding",
  imports: [
    ProviderLogoComponent,
    FormsModule,
    NzDrawerModule,
    NzButtonModule,
    NzInputModule,
    NzAlertModule,
    NzTagModule,
  ],
  templateUrl: "./provider-onboarding.component.html",
  styleUrl: "./provider-onboarding.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProviderOnboardingComponent {
  readonly visible = input(false);
  readonly organizationId = input.required<string>();
  readonly catalog = input<ProviderCatalogItem[]>([]);
  readonly connection = input<ProviderConnection | null>(null);
  readonly closed = output<void>();
  readonly changed = output<void>();
  protected readonly selected = signal<ProviderCatalogItem | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal("");
  protected readonly notice = signal("");
  protected readonly step = signal(0);
  protected readonly choices = signal<Choice[]>([]);
  protected modelSearch = "";
  protected modelFilter = "";
  protected modelTab = "installed";
  protected showMore = false;
  protected readonly recommendations = signal<OllamaRecommendation[]>([]);
  protected readonly pullJob = signal<OllamaPullJob | null>(null);
  protected readonly pullStarting = signal(false);
  private pullPolling?: Subscription;
  protected search = "";
  protected category = "";
  protected name = "";
  protected baseUrl = "";
  protected secret = "";
  protected manualId = "";
  protected manualCapability: ProviderCapability | "UNKNOWN" = "UNKNOWN";
  protected manualDimension: number | null = null;
  private connectionId = "";
  private openedConnectionId: string | null | undefined;
  private readonly api = inject(ProviderApiService);
  private readonly destroyRef = inject(DestroyRef);
  constructor() {
    effect(() => {
      if (!this.visible()) {
        this.openedConnectionId = undefined;
        this.pullPolling?.unsubscribe();
        return;
      }
      const existing = this.connection();
      const openingId = existing?.id ?? null;
      if (this.openedConnectionId === openingId) return;
      this.openedConnectionId = openingId;
      this.connectionId = existing?.id ?? "";
      this.name = existing?.name ?? "";
      this.baseUrl = existing?.base_url ?? "";
      this.secret = "";
      this.search = "";
      this.manualId = "";
      this.modelSearch = "";
      this.modelFilter = "";
      this.error.set("");
      this.notice.set("");
      this.choices.set([]);
      this.pullJob.set(null);
      this.recommendations.set([]);
      this.modelTab = "installed";
      this.showMore = false;
      this.step.set(existing ? 1 : 0);
      const catalog = untracked(() => this.catalog());
      const selected = existing
        ? (catalog.find(
          (item) => item.id === (existing.catalog_id ?? resolveLegacyCatalogId(existing)),
        ) ?? null)
        : null;
      this.selected.set(selected);
      this.manualCapability = selected?.capabilities.length === 1 ? selected.capabilities[0] : "UNKNOWN";
    });
  }
  protected filteredCatalog() {
    return this.catalog().filter(
      (item) =>
        item.name.toLowerCase().includes(this.search.toLowerCase()) &&
        (!this.category || item.category === this.category),
    );
  }
  protected choose(item: ProviderCatalogItem) {
    if (item.status !== "SUPPORTED" || this.busy()) return;
    this.selected.set(item);
    this.name = item.name;
    this.baseUrl = item.default_base_url ?? "";
    this.secret = "";
    this.manualCapability = item.capabilities.length === 1 ? item.capabilities[0] : "UNKNOWN";
    this.step.set(1);
  }
  protected test() {
    const item = this.selected();
    if (!item?.provider_type || !this.name.trim() || this.busy()) return;
    if (item.id === "compatible" && !this.baseUrl.trim()) {
      this.error.set("Nhập Base URL của provider OpenAI-compatible.");
      return;
    }
    this.busy.set(true);
    this.error.set("");
    this.notice.set("");
    const payload = {
      catalog_id: item.id,
      name: this.name.trim(),
      base_url: this.baseUrl.trim() || null,
      ...(this.secret ? { secret: this.secret } : {}),
    };
    const request = this.connectionId
      ? this.api.update(this.connectionId, payload)
      : this.api.create(this.organizationId(), {
        ...payload,
        provider_type: item.provider_type,
      });
    request
      .pipe(
        switchMap((connection) => {
          this.connectionId = connection.id;
          this.secret = "";
          this.changed.emit();
          return this.api.test(connection.id);
        }),
        switchMap((result) => {
          if (
            result.error_code &&
            result.error_code !== "MODEL_DISCOVERY_UNSUPPORTED"
          ) {
            this.error.set(
              apiError({ error: { error: { code: result.error_code } } }),
            );
            return of(null);
          }
          this.notice.set(
            result.status === "CONNECTED"
              ? `Kết nối thành công · ${result.latency_ms} ms`
              : "Nhập Model ID thủ công để kiểm tra và đăng ký model.",
          );
          this.step.set(2);
          return forkJoin({
            discovered: item.supports_model_discovery && !result.error_code
              ? this.api.discover(this.connectionId) : of([]),
            registered: this.api.models(this.organizationId()),
          });
        }),
        finalize(() => {
          this.busy.set(false);
          this.changed.emit();
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (result) => {
          if (!result) return;
          this.choices.set(
            result.discovered.map((model) => ({
              ...model,
              selected: false,
              registered: result.registered.some(m => m.connection_id === this.connectionId && m.model === model.model),
              capability: model.capabilities.length === 1 ? model.capabilities[0] : "UNKNOWN",
            })),
          );
          if (item.provider_type === "OLLAMA") this.loadOllama();
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected addManual() {
    const model = this.manualId.trim();
    if (!model || this.manualCapability === "UNKNOWN" || this.choices().some((item) => item.model === model)) return;
    const capability = this.manualCapability;
    this.choices.update((items) => [
      ...items,
      {
        model,
        display_name: model,
        capabilities: [capability],
        capability,
        dimension: this.manualDimension,
        selected: true,
        registered: false,
      },
    ]);
    this.manualId = "";
    this.manualDimension = null;
  }
  protected save() {
    const selected = this.choices().filter((item) => item.selected && !item.registered);
    if (!selected.length || this.busy() || !this.connectionId) return;
    if (selected.some(item => item.capability === "UNKNOWN")) {
      this.error.set("Chọn chức năng cho mọi model UNKNOWN trước khi đăng ký.");
      return;
    }
    this.busy.set(true);
    this.error.set("");
    from(selected)
      .pipe(
        concatMap((item) =>
          this.api.register(this.connectionId, {
            model: item.model,
            display_name: item.display_name ?? item.model,
            capability: item.capability as ProviderCapability,
            ...(item.capability === "EMBEDDING"
              ? { dimension: item.dimension || null }
              : {}),
          }),
        ),
        finalize(() => {
          this.busy.set(false);
          this.changed.emit();
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (registered) => {
          this.choices.update((items) =>
            items.map((item) => item.model === registered.model
              ? { ...item, registered: true, selected: false } : item),
          );
          this.notice.set(`Đã đăng ký ${registered.model}.`);
        },
        error: (error) => this.error.set(apiError(error)),
        complete: () => {
          this.busy.set(false);
          this.close();
        },
      });
  }
  protected close() {
    if (this.busy()) return;
    this.secret = "";
    this.pullPolling?.unsubscribe();
    this.changed.emit();
    this.closed.emit();
  }
  protected hasSelection() {
    return this.choices().some((item) => item.selected && !item.registered)
      && !this.choices().some(item => item.selected && item.capability === "UNKNOWN");
  }
  protected filteredChoices() {
    const search = this.modelSearch.trim().toLowerCase();
    return this.choices().filter(item =>
      `${item.model} ${item.display_name ?? ''}`.toLowerCase().includes(search)
      && (!this.modelFilter || item.capability === this.modelFilter));
  }
  protected selectedCount() { return this.choices().filter(item => item.selected && !item.registered).length; }
  protected allFilteredSelected() {
    const items = this.filteredChoices().filter(item => !item.registered);
    return items.length > 0 && items.every(item => item.selected);
  }
  protected someFilteredSelected() {
    return this.filteredChoices().some(item => item.selected && !item.registered) && !this.allFilteredSelected();
  }
  protected selectFiltered(value: boolean) {
    if (this.busy()) return;
    const models = new Set(this.filteredChoices().filter(item => !item.registered).map(item => item.model));
    this.choices.update(items => items.map(item => models.has(item.model) ? {...item, selected: value} : item));
  }
  protected formatBytes(bytes: number | null | undefined) {
    if (!bytes) return '—';
    return bytes >= 1_000_000_000 ? `${(bytes / 1_000_000_000).toFixed(1)} GB` : `${Math.round(bytes / 1_000_000)} MB`;
  }
  protected pullActive() { return ['QUEUED', 'PULLING', 'VERIFYING'].includes(this.pullJob()?.status ?? '') || this.pullStarting(); }
  protected installed(model: string) { return this.choices().some(item => item.model === model); }
  protected visibleRecommendations() { return this.recommendations().filter(item => this.showMore || item.highlighted); }
  private loadOllama() {
    forkJoin({ recommendations: this.api.ollamaRecommendations(this.connectionId), jobs: this.api.ollamaPulls(this.connectionId) })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: ({recommendations, jobs}) => {
          this.recommendations.set(recommendations);
          if (jobs[0]) { this.pullJob.set(jobs[0]); if (this.pullActive()) this.pollPull(jobs[0].id); }
        }, error: error => this.error.set(apiError(error)),
      });
  }
  protected install(model: string) {
    if (!model.trim() || this.pullActive() || this.busy()) return;
    this.error.set('');
    this.pullStarting.set(true);
    this.api.pullOllama(this.connectionId, model.trim()).pipe(finalize(() => this.pullStarting.set(false)), takeUntilDestroyed(this.destroyRef))
      .subscribe({next: job => { this.pullJob.set(job); this.pollPull(job.id); }, error: error => this.error.set(apiError(error))});
  }
  protected pullPercent() {
    const job = this.pullJob();
    return job?.total_bytes ? Math.min(100, Math.round(100 * job.completed_bytes / job.total_bytes)) : 0;
  }
  private pollPull(jobId: string) {
    this.pullPolling?.unsubscribe();
    this.pullPolling = timer(0, 1500).pipe(
      exhaustMap(() => this.api.ollamaPull(this.connectionId, jobId)),
      takeWhile(job => ['QUEUED', 'PULLING', 'VERIFYING'].includes(job.status), true),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: job => {
        this.pullJob.set(job);
        if (job.status === 'READY') {
          this.notice.set(`Đã cài đặt ${job.model}${job.registered_model_id ? ' và đăng ký' : ''}.`);
          this.modelTab = 'installed';
          this.changed.emit();
        }
        if (job.status === 'READY' || job.status === 'FAILED') {
          forkJoin({ discovered: this.api.discover(this.connectionId), registered: this.api.models(this.organizationId()) })
            .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({next: result => {
              this.choices.set(result.discovered.map(model => ({ ...model, selected: false, capability: 'CHAT', registered: result.registered.some(item => item.connection_id === this.connectionId && item.model === model.model) })));
            }, error: error => this.error.set(apiError(error))});
        }
        if (job.status === 'FAILED') this.error.set('Cài đặt hoặc kiểm tra model thất bại. Kiểm tra Ollama và thử lại; model đã tải vẫn nằm trong Installed.');
      }, error: error => this.error.set(apiError(error)),
    });
  }
}
