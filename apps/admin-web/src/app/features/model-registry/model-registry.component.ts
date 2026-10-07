import { DatePipe } from "@angular/common";
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { FormsModule } from "@angular/forms";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzSelectModule } from "ng-zorro-antd/select";
import { NzTableModule } from "ng-zorro-antd/table";
import { NzTagModule } from "ng-zorro-antd/tag";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { finalize } from "rxjs";
import { NzPopconfirmModule } from "ng-zorro-antd/popconfirm";
import {
  ProviderApiService,
  RegistryModel,
} from "../../core/api/provider-api.service";
import { RaghubApiService } from "../../core/raghub-api.service";
import { session } from "../../core/api-auth.interceptor";
import { consoleOrganization } from "../../core/console-organization";
import { apiError } from "../../core/api/api-error";
import { ProviderLogoComponent } from "../../shared/provider-logo/provider-logo.component";
import { AiModuleTabsComponent } from "../ai-navigation/ai-module-tabs.component";

@Component({
  selector: "raghub-model-registry",
  imports: [
    ProviderLogoComponent,
    AiModuleTabsComponent,
    DatePipe,
    FormsModule,
    NzButtonModule,
    NzInputModule,
    NzSelectModule,
    NzTableModule,
    NzTagModule,
    NzAlertModule,
    NzPopconfirmModule,
  ],
  template: `<main class="selfhost-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">AI & Models / System</p>
        <h1>Model Registry</h1>
        <p>Model đã đăng ký từ các Provider Connection.</p>
      </div>
    </header>
    <raghub-ai-module-tabs />
    @if (error()) {
      <nz-alert nzType="error" [nzMessage]="error()" nzShowIcon />
    }
    <div class="toolbar">
      <input
        nz-input
        aria-label="Tìm model"
        placeholder="Tìm model hoặc provider…"
        [ngModel]="query()"
        (ngModelChange)="query.set($event)"
      /><nz-select aria-label="Chức năng model" nzPlaceHolder="Tất cả chức năng" [ngModel]="capability()" (ngModelChange)="capability.set($event)">
        <nz-option nzValue="" nzLabel="Tất cả chức năng" />
        <nz-option nzValue="CHAT" nzLabel="Chat" />
        <nz-option nzValue="EMBEDDING" nzLabel="Embedding" />
        <nz-option nzValue="RERANK" nzLabel="Rerank" />
      </nz-select><nz-select aria-label="Trạng thái model" nzPlaceHolder="Tất cả trạng thái" [ngModel]="availability()" (ngModelChange)="availability.set($event)">
        <nz-option nzValue="" nzLabel="Tất cả trạng thái" />
        <nz-option nzValue="AVAILABLE" nzLabel="Khả dụng" />
        <nz-option nzValue="UNAVAILABLE" nzLabel="Không khả dụng" />
        <nz-option nzValue="UNTESTED" nzLabel="Chưa kiểm tra" />
        <nz-option nzValue="DISABLED" nzLabel="Đã tắt" />
      </nz-select><button nz-button (click)="load()" [nzLoading]="loading()">
        Làm mới
      </button>
    </div>
    <nz-table
      #table
      [nzData]="filtered()"
      [nzLoading]="loading()"
      [nzPageSize]="10"
      [nzScroll]="{ x: '1000px' }"
      ><thead>
        <tr>
          <th>Model</th>
          <th>Provider</th>
          <th>Chức năng</th>
          <th>Dimension</th>
          <th>Trạng thái</th>
          <th>Workspace sử dụng</th>
          <th>Kiểm tra gần nhất</th>
          <th>Thao tác</th>
        </tr>
      </thead>
      <tbody>
        @for (model of table.data; track model.id) {
          <tr>
            <td>
              <strong>{{ model.display_name || model.model }}</strong
              ><small class="block muted">{{ model.model }}</small>
            </td>
            <td>
              <div class="provider-model">
                <raghub-provider-logo
                  [catalogId]="model.provider_catalog_id"
                  size="sm"
                /><span
                  >{{ model.provider_name
                  }}<small class="block muted">{{
                    model.connection_status
                  }}</small></span
                >
              </div>
            </td>
            <td>
              <nz-tag>{{ model.capability }}</nz-tag>
            </td>
            <td>{{ model.dimension ?? "—" }}</td>
            <td>
              <nz-tag
                [nzColor]="
                  model.availability_status === 'AVAILABLE'
                    ? 'green'
                    : 'default'
                "
                >{{ model.availability_status }}</nz-tag
              >
            </td>
            <td>{{ model.used_by_workspaces }}</td>
            <td>
              {{
                model.last_health_check_at
                  ? (model.last_health_check_at | date: "dd/MM/yyyy HH:mm")
                  : "Chưa kiểm tra"
              }}
            </td>
            <td>
              <div class="card-actions">
                <button
                  nz-button
                  (click)="test(model)"
                  [disabled]="
                    !!busy() || !model.enabled || !model.connection_enabled
                  "
                  [nzLoading]="busy() === model.id"
                >
                  Kiểm tra</button
                ><button
                  nz-button
                  (click)="toggle(model)"
                  [disabled]="!!busy()"
                >
                  {{ model.enabled ? "Tắt" : "Bật" }}
                </button>
              </div>
            </td>
          </tr>
        }
      </tbody></nz-table
    >
  </main>`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ModelRegistryComponent {
  protected readonly models = signal<RegistryModel[]>([]);
  protected readonly loading = signal(false);
  protected readonly busy = signal("");
  protected readonly error = signal("");
  protected readonly query = signal("");
  protected readonly capability = signal("");
  protected readonly availability = signal("");
  protected readonly filtered = computed(() =>
    this.models().filter(
      (model) =>
        (!this.capability() || model.capability === this.capability()) &&
        (!this.availability() ||
          model.availability_status === this.availability()) &&
        `${model.model} ${model.provider_name}`
          .toLowerCase()
          .includes(this.query().toLowerCase()),
    ),
  );
  private readonly api = inject(ProviderApiService);
  private readonly auth = inject(RaghubApiService);
  private readonly destroyRef = inject(DestroyRef);
  private organizationId = "";
  constructor() {
    this.auth
      .organizations()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (items) => {
          this.organizationId = consoleOrganization(items)?.id ?? "";
          session.organizationId = this.organizationId || null;
          this.load();
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected load() {
    if (!this.organizationId) return;
    this.loading.set(true);
    this.api
      .models(this.organizationId)
      .pipe(
        finalize(() => this.loading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (items) => this.models.set(items),
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected test(model: RegistryModel) {
    if (this.busy()) return;
    this.busy.set(model.id);
    this.error.set("");
    this.api
      .testModel(model.id)
      .pipe(
        finalize(() => {
          this.busy.set("");
          this.load();
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({ error: (error) => this.error.set(apiError(error)) });
  }
  protected remove(model: RegistryModel) {
    if (this.busy()) return;
    this.busy.set(model.id);
    this.error.set("");
    this.api
      .removeModel(model.id)
      .pipe(
        finalize(() => {
          this.busy.set("");
          this.load();
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({ error: (error) => this.error.set(apiError(error)) });
  }
  protected toggle(model: RegistryModel) {
    if (this.busy()) return;
    this.busy.set(model.id);
    this.error.set("");
    this.api
      .updateModel(model.id, !model.enabled)
      .pipe(
        finalize(() => {
          this.busy.set("");
          this.load();
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({ error: (error) => this.error.set(apiError(error)) });
  }
}
