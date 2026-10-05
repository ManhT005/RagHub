import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
import { RouterLink } from "@angular/router";
import { DatabaseOutline } from "@ant-design/icons-angular/icons";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzIconModule, provideNzIconsPatch } from "ng-zorro-antd/icon";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzModalModule } from "ng-zorro-antd/modal";
import { NzSelectModule } from "ng-zorro-antd/select";
import { NzSpinModule } from "ng-zorro-antd/spin";
import { catchError, forkJoin, map, of } from "rxjs";
import { NzTableModule } from "ng-zorro-antd/table";

import { session } from "../core/api-auth.interceptor";
import {
  Organization,
  RaghubApiService,
  Workspace,
} from "../core/raghub-api.service";
import { WorkspaceAccessComponent } from "../workspace-console/workspace-access.component";

@Component({
  selector: "raghub-workspaces",
  imports: [
    FormsModule,
    RouterLink,
    NzAlertModule,
    NzButtonModule,
    NzIconModule,
    NzInputModule,
    NzModalModule,
    NzSelectModule,
    NzSpinModule,
    NzTableModule,
    WorkspaceAccessComponent,
  ],
  providers: [provideNzIconsPatch([DatabaseOutline])],
  templateUrl: "./workspaces.component.html",
  styleUrl: "./workspaces.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspacesComponent {
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly docCounts = signal<Partial<Record<string, number>>>({});
  protected readonly botCounts = signal<Partial<Record<string, number>>>({});
  protected readonly loading = signal(true);
  protected readonly error = signal("");
  protected readonly search = signal("");
  protected readonly isCreateFormOpen = signal(false);
  protected readonly accessWorkspace = signal<Workspace | null>(null);

  protected selectedOrganization = session.organizationId ?? "";
  protected name = "";
  protected slug = "";

  protected readonly selectedOrganizationData = computed(() =>
    this.organizations().find((item) => item.id === this.selectedOrganization),
  );
  protected readonly isAdmin = computed(
    () => this.selectedOrganizationData()?.role === "ADMIN",
  );
  protected readonly filteredWorkspaces = computed(() => {
    const keyword = this.search().trim().toLowerCase();
    if (!keyword) return this.workspaces();
    return this.workspaces().filter(
      (workspace) =>
        workspace.name.toLowerCase().includes(keyword) ||
        workspace.slug.toLowerCase().includes(keyword),
    );
  });

  private readonly api = inject(RaghubApiService);

  constructor() {
    this.loadOrganizations();
  }


  protected loadOrganizations(): void {
    this.loading.set(true);
    this.api.organizations().subscribe({
      next: (organizations) => {
        this.organizations.set(organizations);
        if (!this.selectedOrganization && organizations[0]) {
          this.selectedOrganization = organizations[0].id;
        }
        this.changeOrganization();
      },
      error: () => {
        this.loading.set(false);
        this.error.set("Không thể tải tổ chức. Hãy đăng nhập lại rồi thử lần nữa.");
      },
    });
  }

  protected changeOrganization(): void {
    session.organizationId = this.selectedOrganization || null;
    if (!this.selectedOrganization) {
      this.loading.set(false);
      return;
    }
    this.loading.set(true);
    this.error.set("");
    this.api.workspaces().subscribe({
      next: (items) => {
        this.workspaces.set(items);
        this.loadCounts(items);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set("Không thể tải danh sách workspace. Hãy thử lại.");
      },
    });
  }


  private loadCounts(items: Workspace[]): void {
    if (!items.length) {
      this.docCounts.set({});
      this.botCounts.set({});
      return;
    }
    forkJoin({
      docs: forkJoin(
        items.map((workspace) =>
          this.api.documents(workspace.id).pipe(
            map((documents) => ({ id: workspace.id, count: documents.length })),
            catchError(() => of({ id: workspace.id, count: 0 })),
          ),
        ),
      ),
      bots: forkJoin(
        items.map((workspace) =>
          this.api.chatbots(workspace.id).pipe(
            map((chatbots) => ({ id: workspace.id, count: chatbots.length })),
            catchError(() => of({ id: workspace.id, count: 0 })),
          ),
        ),
      ),
    }).subscribe(({ docs, bots }) => {
      this.docCounts.set(Object.fromEntries(docs.map((item) => [item.id, item.count])));
      this.botCounts.set(Object.fromEntries(bots.map((item) => [item.id, item.count])));
    });
  }

  protected create(): void {
    const name = this.name.trim();
    let slug = this.slug.trim().toLowerCase();
    if (!slug && name) {
      slug = name
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
    }
    if (!name || !slug) {
      this.error.set("Nhập tên và mã định danh workspace.");
      return;
    }
    this.api.createWorkspace(name, slug).subscribe({
      next: (workspace) => {
        this.workspaces.update((items) => [...items, workspace]);
        this.docCounts.update((counts) => ({ ...counts, [workspace.id]: 0 }));
        this.botCounts.update((counts) => ({ ...counts, [workspace.id]: 0 }));
        this.name = "";
        this.slug = "";
        this.error.set("");
        this.isCreateFormOpen.set(false);
      },
      error: () =>
        this.error.set("Không thể tạo workspace. Mã định danh có thể đã được sử dụng."),
    });
  }
  protected toggleCreateForm(): void {
    this.isCreateFormOpen.update((isOpen) => !isOpen);
  }

  protected openAccess(workspace: Workspace): void {
    this.accessWorkspace.set(workspace);
  }

  protected closeAccess(): void {
    this.accessWorkspace.set(null);
  }

  protected cancelCreate(): void {
    this.name = "";
    this.slug = "";
    this.error.set("");
    this.isCreateFormOpen.set(false);
  }
}
