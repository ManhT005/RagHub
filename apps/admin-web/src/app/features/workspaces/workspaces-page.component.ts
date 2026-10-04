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
import { ActivatedRoute, RouterLink } from "@angular/router";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzTableModule } from "ng-zorro-antd/table";
import { NzTagModule } from "ng-zorro-antd/tag";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzModalModule } from "ng-zorro-antd/modal";
import { NzDropDownModule } from "ng-zorro-antd/dropdown";
import { NzPopconfirmModule } from "ng-zorro-antd/popconfirm";
import { catchError, finalize, map, of, switchMap } from "rxjs";
import {
  WorkspaceApiService,
  WorkspaceSummary,
} from "../../core/api/workspace-api.service";
import {
  ProviderApiService,
  RegistryModel,
  selectableModel,
} from "../../core/api/provider-api.service";
import { RaghubApiService, Organization } from "../../core/raghub-api.service";
import { session } from "../../core/api-auth.interceptor";
import { apiError } from "../../core/api/api-error";
import { ProviderLogoComponent } from '../../shared/provider-logo/provider-logo.component';
import { shortModelName } from '../../core/provider-brand/provider-brand.registry';

@Component({
  selector: "raghub-workspaces-page",
  imports: [
    ProviderLogoComponent,
    DatePipe,
    FormsModule,
    RouterLink,
    NzButtonModule,
    NzInputModule,
    NzTableModule,
    NzTagModule,
    NzAlertModule,
    NzModalModule,
    NzDropDownModule,
    NzPopconfirmModule,
  ],
  templateUrl: "./workspaces-page.component.html",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspacesPageComponent {
  protected readonly shortModelName = shortModelName;
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly selectedOrganization = signal(
    session.organizationId ?? "",
  );
  protected readonly isAdmin = computed(
    () =>
      this.organizations().find(
        (item) => item.id === this.selectedOrganization(),
      )?.role === "ADMIN",
  );
  protected readonly workspaces = signal<WorkspaceSummary[]>([]);
  protected readonly models = signal<RegistryModel[]>([]);
  protected readonly loading = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal("");
  protected readonly notice = signal("");
  protected readonly search = signal("");
  protected readonly status = signal("");
  protected readonly sort = signal("newest");
  protected readonly editorOpen = signal(false);
  protected readonly editing = signal<WorkspaceSummary | null>(null);
  protected readonly filtered = computed(() =>
    this.workspaces()
      .filter(
        (item) =>
          `${item.name} ${item.slug}`
            .toLowerCase()
            .includes(this.search().toLowerCase()) &&
          (!this.status() || item.status === this.status()),
      )
      .sort((a, b) =>
        this.sort() === "name"
          ? a.name.localeCompare(b.name)
          : (b.updated_at ?? b.created_at).localeCompare(
            a.updated_at ?? a.created_at,
          ),
      ),
  );
  protected name = "";
  protected slug = "";
  protected initialModel = "";
  private readonly api = inject(WorkspaceApiService);
  private readonly providers = inject(ProviderApiService);
  private readonly auth = inject(RaghubApiService);
  private readonly destroyRef = inject(DestroyRef);
  constructor() {
    if (inject(ActivatedRoute).snapshot.queryParamMap.get("denied"))
      this.error.set("Bạn không có quyền truy cập workspace này.");
    this.auth
      .organizations()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (items) => {
          this.organizations.set(items);
          if (!items.some((item) => item.id === this.selectedOrganization()))
            this.selectedOrganization.set(items[0]?.id ?? "");
          this.changeOrganization();
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected changeOrganization() {
    session.organizationId = this.selectedOrganization() || null;
    this.workspaces.set([]);
    this.models.set([]);
    if (!this.selectedOrganization()) return;
    this.load();
    if (this.isAdmin())
      this.providers
        .models(this.selectedOrganization())
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (items) =>
            this.models.set(
              items.filter(
                (item) =>
                  item.capability === "EMBEDDING" && selectableModel(item),
              ),
            ),
          error: (error) => this.error.set(apiError(error)),
        });
  }
  protected load() {
    this.loading.set(true);
    this.api
      .list()
      .pipe(
        finalize(() => this.loading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (items) => this.workspaces.set(items),
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected open(item: WorkspaceSummary | null = null) {
    this.editing.set(item);
    this.name = item?.name ?? "";
    this.slug = item?.slug ?? "";
    this.initialModel = "";
    this.editorOpen.set(true);
  }
  protected save() {
    if (this.saving() || !this.name.trim()) return;
    const slug =
      this.slug.trim() ||
      this.name
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/đ/g, "d")
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
    if (!/^[a-z0-9][a-z0-9-]{1,99}$/.test(slug)) {
      this.error.set(
        "Mã định danh phải gồm 2–100 ký tự chữ thường, số hoặc dấu gạch ngang.",
      );
      return;
    }
    this.saving.set(true);
    this.error.set("");
    const editing = this.editing();
    const request = editing
      ? this.api.update(editing.id, this.name.trim(), slug)
      : this.api.create(this.name.trim(), slug);
    request
      .pipe(
        switchMap((workspace) =>
          !editing && this.initialModel
            ? this.api.changeEmbedding(workspace.id, this.initialModel).pipe(
              map(() => workspace),
              catchError((error) => {
                this.notice.set(
                  `Workspace đã tạo. ${apiError(error)} Cấu hình model trong cài đặt AI.`,
                );
                return of(workspace);
              }),
            )
            : of(workspace),
        ),
        finalize(() => this.saving.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => {
          this.editorOpen.set(false);
          this.load();
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected remove(item: WorkspaceSummary) {
    if (this.saving()) return;
    this.saving.set(true);
    this.api
      .remove(item.id)
      .pipe(
        finalize(() => this.saving.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => this.load(),
        error: (error) => this.error.set(apiError(error)),
      });
  }

}
