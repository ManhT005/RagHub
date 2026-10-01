import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
import { RouterLink } from "@angular/router";
import { catchError, forkJoin, map, of } from "rxjs";

import { session } from "../core/api-auth.interceptor";
import {
  Membership,
  Organization,
  RaghubApiService,
  Workspace,
} from "../core/raghub-api.service";

@Component({
  selector: "raghub-workspaces",
  imports: [FormsModule, RouterLink],
  templateUrl: "./workspaces.component.html",
  styleUrl: "./workspaces.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspacesComponent {
  protected readonly roleLabel = (role: string): string =>
    ({
      OWNER: "Chủ sở hữu",
      ADMIN: "Quản trị viên",
      EDITOR: "Biên tập viên",
      VIEWER: "Người xem",
    })[role] ?? role;
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly members = signal<Membership[]>([]);
  protected readonly docCounts = signal<Record<string, number>>({});
  protected readonly botCounts = signal<Record<string, number>>({});
  protected readonly search = signal("");
  protected readonly filteredWorkspaces = computed(() => {
    const keyword = this.search().trim().toLowerCase();
    if (!keyword) return this.workspaces();
    return this.workspaces().filter(
      (ws) =>
        ws.name.toLowerCase().includes(keyword) ||
        ws.slug.toLowerCase().includes(keyword),
    );
  });
  protected readonly error = signal("");
  protected selectedOrganization = session.organizationId ?? "";
  protected name = "";
  protected slug = "";
  protected organizationName = "";
  protected organizationSlug = "";
  protected memberEmail = "";
  protected memberRole: Membership["role"] = "EDITOR";
  private readonly api = inject(RaghubApiService);

  constructor() {
    this.loadOrganizations();
  }

  protected loadOrganizations(): void {
    this.api.organizations().subscribe({
      next: (organizations) => {
        this.organizations.set(organizations);
        if (!this.selectedOrganization && organizations[0])
          this.selectedOrganization = organizations[0].id;
        this.changeOrganization();
      },
      error: () => this.error.set("Hãy đăng nhập, sau đó chọn một tổ chức."),
    });
  }

  protected changeOrganization(): void {
    session.organizationId = this.selectedOrganization || null;
    if (!this.selectedOrganization) return;
    this.api.workspaces().subscribe({
      next: (items) => {
        this.workspaces.set(items);
        this.loadCounts(items);
      },
      error: () =>
        this.error.set("Không thể tải danh sách không gian làm việc."),
    });
    this.api
      .members(this.selectedOrganization)
      .subscribe({
        next: (items) => this.members.set(items),
        error: () => this.members.set([]),
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
        items.map((ws) =>
          this.api.documents(ws.id).pipe(
            map((docs) => ({ id: ws.id, count: docs.length })),
            catchError(() => of({ id: ws.id, count: 0 })),
          ),
        ),
      ),
      bots: forkJoin(
        items.map((ws) =>
          this.api.chatbots(ws.id).pipe(
            map((bots) => ({ id: ws.id, count: bots.length })),
            catchError(() => of({ id: ws.id, count: 0 })),
          ),
        ),
      ),
    }).subscribe(({ docs, bots }) => {
      this.docCounts.set(Object.fromEntries(docs.map((d) => [d.id, d.count])));
      this.botCounts.set(Object.fromEntries(bots.map((b) => [b.id, b.count])));
    });
  }

  protected createOrganization(): void {
    this.api
      .createOrganization(this.organizationName, this.organizationSlug)
      .subscribe({
        next: (organization) => {
          this.organizations.update((items) => [...items, organization]);
          this.selectedOrganization = organization.id;
          this.organizationName = "";
          this.organizationSlug = "";
          this.changeOrganization();
        },
        error: () =>
          this.error.set(
            "Không thể tạo tổ chức. Mã định danh có thể đã được sử dụng.",
          ),
      });
  }

  protected saveMember(): void {
    if (!this.selectedOrganization) return;
    this.api
      .saveMember(this.selectedOrganization, this.memberEmail, this.memberRole)
      .subscribe({
        next: (member) => {
          this.members.update((items) => [
            ...items.filter((item) => item.user_id !== member.user_id),
            member,
          ]);
          this.memberEmail = "";
        },
        error: () =>
          this.error.set(
            "Không thể thêm thành viên. Tài khoản người này chưa tồn tại.",
          ),
      });
  }

  protected removeMember(member: Membership): void {
    if (!this.selectedOrganization || member.role === "OWNER") return;
    this.api.deleteMember(this.selectedOrganization, member.user_id).subscribe({
      next: () =>
        this.members.update((items) =>
          items.filter((item) => item.user_id !== member.user_id),
        ),
      error: () => this.error.set("Không thể xóa thành viên."),
    });
  }

  protected create(): void {
    const name = this.name.trim();
    let slug = this.slug.trim().toLowerCase();
    if (!slug && name)
      slug = name
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
    if (!name || !slug) {
      this.error.set("Nhập tên và mã định danh (slug: chữ thường, số, dấu -).");
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
      },
      error: () =>
        this.error.set(
          "Không thể tạo không gian làm việc. Mã định danh có thể đã được sử dụng.",
        ),
    });
  }
}
