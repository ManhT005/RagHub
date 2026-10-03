import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzPopconfirmModule } from "ng-zorro-antd/popconfirm";
import { NzSpinModule } from "ng-zorro-antd/spin";
import { NzTableModule } from "ng-zorro-antd/table";
import { NzTagModule } from "ng-zorro-antd/tag";

import { Membership, RaghubApiService } from "../core/raghub-api.service";

@Component({
  selector: "raghub-workspace-access",
  imports: [
    FormsModule,
    NzAlertModule,
    NzButtonModule,
    NzInputModule,
    NzPopconfirmModule,
    NzSpinModule,
    NzTableModule,
    NzTagModule,
  ],
  templateUrl: "./workspace-access.component.html",
  styleUrl: "./workspace-access.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceAccessComponent {
  readonly organizationId = input.required<string>();
  readonly workspaceId = input.required<string>();
  readonly workspaceName = input.required<string>();
  readonly isAdmin = input(false);

  protected readonly members = signal<Membership[]>([]);
  protected readonly workspaceAdmins = computed(() =>
    this.members().filter(
      (member) =>
        member.role === "WORKSPACE_ADMIN" &&
        member.workspace_ids.includes(this.workspaceId()),
    ),
  );
  protected readonly loading = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal("");
  protected readonly success = signal("");
  protected email = "";

  private readonly api = inject(RaghubApiService);

  constructor() {
    effect(() => {
      const organizationId = this.organizationId();
      const workspaceId = this.workspaceId();
      if (!this.isAdmin() || !organizationId || !workspaceId) {
        this.members.set([]);
        return;
      }
      this.loadMembers(organizationId);
    });
  }

  protected addAdmin(): void {
    const email = this.email.trim().toLowerCase();
    this.error.set("");
    this.success.set("");
    if (!email) {
      this.error.set("Nhập email tài khoản cần cấp quyền.");
      return;
    }

    const existing = this.members().find(
      (member) => member.email.toLowerCase() === email,
    );
    if (existing?.role === "ADMIN") {
      this.error.set("Tài khoản này đã là Admin và có quyền trên mọi workspace.");
      return;
    }

    const workspaceIds = [
      ...new Set([...(existing?.workspace_ids ?? []), this.workspaceId()]),
    ];
    this.saving.set(true);
    this.api
      .saveMember(this.organizationId(), email, "WORKSPACE_ADMIN", workspaceIds)
      .subscribe({
        next: (member) => {
          this.members.update((items) => [
            ...items.filter((item) => item.user_id !== member.user_id),
            member,
          ]);
          this.email = "";
          this.saving.set(false);
          this.success.set("Đã thêm quản trị viên vào workspace.");
        },
        error: () => {
          this.saving.set(false);
          this.error.set(
            "Không thể cấp quyền. Hãy kiểm tra tài khoản đã tồn tại và thử lại.",
          );
        },
      });
  }

  protected removeAdmin(member: Membership): void {
    const remainingWorkspaceIds = member.workspace_ids.filter(
      (workspaceId) => workspaceId !== this.workspaceId(),
    );
    this.error.set("");
    this.success.set("");

    const request = remainingWorkspaceIds.length
      ? this.api.saveMember(
          this.organizationId(),
          member.email,
          "WORKSPACE_ADMIN",
          remainingWorkspaceIds,
        )
      : this.api.deleteMember(this.organizationId(), member.user_id);

    request.subscribe({
      next: () => {
        this.members.update((items) =>
          remainingWorkspaceIds.length
            ? items.map((item) =>
                item.user_id === member.user_id
                  ? { ...item, workspace_ids: remainingWorkspaceIds }
                  : item,
              )
            : items.filter((item) => item.user_id !== member.user_id),
        );
        this.success.set("Đã gỡ quản trị viên khỏi workspace.");
      },
      error: () =>
        this.error.set("Không thể gỡ quyền quản trị. Hãy thử lại."),
    });
  }

  private loadMembers(organizationId: string): void {
    this.loading.set(true);
    this.error.set("");
    this.api.members(organizationId).subscribe({
      next: (members) => {
        this.members.set(members);
        this.loading.set(false);
      },
      error: () => {
        this.members.set([]);
        this.loading.set(false);
        this.error.set("Không thể tải danh sách quản trị viên.");
      },
    });
  }
}