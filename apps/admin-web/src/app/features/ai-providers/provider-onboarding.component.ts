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
import { from, concatMap, finalize, of, switchMap } from "rxjs";
import {
  ProviderApiService,
  ProviderCatalogItem,
  ProviderConnection,
  DiscoveredModel,
} from "../../core/api/provider-api.service";
import { ProviderCapability } from "../../core/raghub-api.service";
import { apiError } from "../../core/api/api-error";
import { resolveLegacyCatalogId } from '../../core/api/provider-catalog-identity';
import { ProviderLogoComponent } from '../../shared/provider-logo/provider-logo.component';

interface Choice extends DiscoveredModel {
  selected: boolean;
  capability: ProviderCapability;
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
  protected search = "";
  protected category = "";
  protected name = "";
  protected baseUrl = "";
  protected secret = "";
  protected manualId = "";
  protected manualCapability: ProviderCapability = "CHAT";
  protected manualDimension: number | null = null;
  private connectionId = "";
  private readonly api = inject(ProviderApiService);
  private readonly destroyRef = inject(DestroyRef);
  constructor() {
    effect(() => {
      if (!this.visible()) return;
      const existing = this.connection();
      this.connectionId = existing?.id ?? "";
      this.name = existing?.name ?? "";
      this.baseUrl = existing?.base_url ?? "";
      this.secret = "";
      this.search = "";
      this.manualId = "";
      this.error.set("");
      this.notice.set("");
      this.choices.set([]);
      this.step.set(existing ? 1 : 0);
      const catalog = untracked(() => this.catalog());
      const selected = existing
        ? (catalog.find(
          (item) => item.id === (existing.catalog_id ?? resolveLegacyCatalogId(existing)),
        ) ?? null)
        : null;
      this.selected.set(selected);
      this.manualCapability = selected?.capabilities[0] ?? "CHAT";
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
    this.manualCapability = item.capabilities[0];
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
          return item.supports_model_discovery && !result.error_code
            ? this.api.discover(this.connectionId)
            : of([]);
        }),
        finalize(() => {
          this.busy.set(false);
          this.changed.emit();
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (models) => {
          if (!models) return;
          this.choices.set(
            models.map((model) => ({
              ...model,
              selected: false,
              capability: model.capabilities[0] ?? item.capabilities[0],
            })),
          );
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected addManual() {
    const model = this.manualId.trim();
    if (!model || this.choices().some((item) => item.model === model)) return;
    this.choices.update((items) => [
      ...items,
      {
        model,
        display_name: model,
        capabilities: [this.manualCapability],
        capability: this.manualCapability,
        dimension: this.manualDimension,
        selected: true,
      },
    ]);
    this.manualId = "";
    this.manualDimension = null;
  }
  protected save() {
    const selected = this.choices().filter((item) => item.selected);
    if (!selected.length || this.busy() || !this.connectionId) return;
    this.busy.set(true);
    this.error.set("");
    from(selected)
      .pipe(
        concatMap((item) =>
          this.api.register(this.connectionId, {
            model: item.model,
            display_name: item.display_name ?? item.model,
            capability: item.capability,
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
            items.filter((item) => item.model !== registered.model),
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
    this.changed.emit();
    this.closed.emit();
  }
  protected hasSelection() {
    return this.choices().some((item) => item.selected);
  }
}
