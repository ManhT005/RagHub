import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  signal,
} from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { FormsModule } from "@angular/forms";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzEmptyModule } from "ng-zorro-antd/empty";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzModalModule } from "ng-zorro-antd/modal";
import { NzPopconfirmModule } from "ng-zorro-antd/popconfirm";
import { NzSelectModule } from "ng-zorro-antd/select";
import { NzSpinModule } from "ng-zorro-antd/spin";
import { NzTableModule } from "ng-zorro-antd/table";
import { NzTagModule } from "ng-zorro-antd/tag";
import { debounceTime, distinctUntilChanged, Subject } from "rxjs";

import { session } from "../core/api-auth.interceptor";
import { consoleOrganization } from "../core/console-organization";
import {
  AdminUser,
  Organization,
  RaghubApiService,
} from "../core/raghub-api.service";

const PAGE_SIZE = 10;

@Component({
  selector: "raghub-users",
  imports: [
    FormsModule,
    NzAlertModule,
    NzButtonModule,
    NzEmptyModule,
    NzInputModule,
    NzModalModule,
    NzPopconfirmModule,
    NzSelectModule,
    NzSpinModule,
    NzTableModule,
    NzTagModule,
  ],
  templateUrl: "./users.component.html",
  styleUrl: "./users.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UsersComponent {
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly users = signal<AdminUser[]>([]);
  protected readonly total = signal(0);
  protected readonly page = signal(1);
  protected readonly pageSize = PAGE_SIZE;
  protected readonly loading = signal(true);
  protected readonly error = signal("");
  protected readonly actionError = signal("");
  protected readonly success = signal("");
  protected readonly searchInput = signal("");
  protected readonly modalOpen = signal(false);
  protected readonly creating = signal(false);
  protected readonly newEmail = signal("");
  protected readonly newPassword = signal("");
  protected readonly newDisplayName = signal("");
  protected readonly updatingId = signal<string | null>(null);
  protected readonly renameOpen = signal(false);
  protected readonly renaming = signal(false);
  protected readonly renameId = signal<string | null>(null);
  protected readonly renameValue = signal("");

  protected selectedOrganization = session.organizationId ?? "";

  protected readonly isAdmin = computed(
    () =>
      this.organizations().find((item) => item.id === this.selectedOrganization)
        ?.role === "ADMIN",
  );
  protected readonly totalPages = computed(() =>
    Math.max(1, Math.ceil(this.total() / this.pageSize)),
  );

  protected readonly roleLabel = (role: AdminUser["role"]): string =>
    role === "ADMIN" ? "Admin" : "Workspace admin";

  protected readonly displayNameOf = (user: AdminUser): string =>
    user.display_name?.trim() ? user.display_name : "—";

  private readonly api = inject(RaghubApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly searchChanges = new Subject<string>();

  constructor() {
    this.searchChanges
      .pipe(
        debounceTime(350),
        distinctUntilChanged(),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.page.set(1);
        this.loadUsers();
      });
    this.loadOrganizations();
  }

  protected loadOrganizations(): void {
    this.loading.set(true);
    this.api.organizations().subscribe({
      next: (organizations) => {
        this.organizations.set(organizations);
        this.selectedOrganization =
          consoleOrganization(organizations)?.id ?? "";
        this.changeOrganization();
      },
      error: () => {
        this.loading.set(false);
        this.error.set(
          "Không thể tải tổ chức. Hãy đăng nhập lại rồi thử lần nữa.",
        );
      },
    });
  }

  protected changeOrganization(): void {
    session.organizationId = this.selectedOrganization || null;
    this.page.set(1);
    this.searchInput.set("");
    this.loadUsers();
  }

  protected search(): void {
    this.page.set(1);
    this.loadUsers();
  }

  protected onSearchInputChange(value: string): void {
    this.searchInput.set(value);
    this.searchChanges.next(value.trim());
  }

  protected changePage(index: number): void {
    if (index < 1 || index > this.totalPages()) return;
    this.page.set(index);
    this.loadUsers();
  }

  protected openCreate(): void {
    this.newEmail.set("");
    this.newPassword.set("");
    this.newDisplayName.set("");
    this.actionError.set("");
    this.success.set("");
    this.modalOpen.set(true);
  }

  protected closeCreate(): void {
    if (this.creating()) return;
    this.modalOpen.set(false);
  }

  protected create(): void {
    const email = this.newEmail().trim().toLowerCase();
    const password = this.newPassword();
    this.actionError.set("");
    this.success.set("");
    if (!email) {
      this.actionError.set("Nhập email của tài khoản cần tạo.");
      return;
    }
    if (password.length < 8) {
      this.actionError.set("Mật khẩu ban đầu phải có ít nhất 8 ký tự.");
      return;
    }
    this.creating.set(true);
    this.api.createAdminUser(email, password, this.newDisplayName()).subscribe({
      next: () => {
        this.creating.set(false);
        this.modalOpen.set(false);
        this.success.set("Đã tạo tài khoản mới.");
        this.loadUsers(true);
      },
      error: (err) => {
        this.creating.set(false);
        this.actionError.set(
          this.describeError(err, "Không thể tạo tài khoản. Hãy thử lại."),
        );
      },
    });
  }

  protected openRename(user: AdminUser): void {
    this.renameId.set(user.id);
    this.renameValue.set(user.display_name ?? "");
    this.actionError.set("");
    this.success.set("");
    this.renameOpen.set(true);
  }

  protected closeRename(): void {
    if (this.renaming()) return;
    this.renameOpen.set(false);
  }

  protected rename(): void {
    const userId = this.renameId();
    if (!userId) return;
    this.actionError.set("");
    this.success.set("");
    this.renaming.set(true);
    this.api.updateAdminUser(userId, this.renameValue()).subscribe({
      next: (updated) => {
        this.renaming.set(false);
        this.renameOpen.set(false);
        this.users.update((items) =>
          items.map((item) => (item.id === updated.id ? updated : item)),
        );
        this.success.set("Đã cập nhật tên hiển thị.");
      },
      error: (err) => {
        this.renaming.set(false);
        this.actionError.set(
          this.describeError(err, "Không thể cập nhật tên. Hãy thử lại."),
        );
      },
    });
  }

  protected toggleStatus(user: AdminUser): void {
    const nextStatus = user.status === "ACTIVE" ? "DISABLED" : "ACTIVE";
    this.updatingId.set(user.id);
    this.actionError.set("");
    this.success.set("");
    this.api.updateAdminUserStatus(user.id, nextStatus).subscribe({
      next: (updated) => {
        this.updatingId.set(null);
        this.users.update((items) =>
          items.map((item) => (item.id === updated.id ? updated : item)),
        );
        this.success.set(
          nextStatus === "ACTIVE"
            ? "Đã kích hoạt quyền truy cập."
            : "Đã vô hiệu hóa quyền truy cập trong phạm vi này.",
        );
      },
      error: (err) => {
        this.updatingId.set(null);
        this.actionError.set(
          this.describeError(err, "Không thể đổi trạng thái. Hãy thử lại."),
        );
      },
    });
  }

  protected formatDate(value: string | null): string {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString("vi-VN");
  }

  private loadUsers(keepPage = false): void {
    if (!this.selectedOrganization) {
      this.loading.set(false);
      this.users.set([]);
      this.total.set(0);
      return;
    }
    if (!keepPage) {
      // page already set by caller
    }
    this.loading.set(true);
    this.error.set("");
    this.api
      .adminUsers(this.searchInput().trim(), this.page(), this.pageSize)
      .subscribe({
        next: (result) => {
          this.users.set(result.items);
          this.total.set(result.total);
          this.page.set(result.page);
          this.loading.set(false);
        },
        error: (err) => {
          this.loading.set(false);
          this.error.set(
            this.describeError(
              err,
              "Không thể tải danh sách người dùng. Hãy thử lại.",
            ),
          );
        },
      });
  }

  private describeError(err: unknown, fallback: string): string {
    const code =
      (err as { error?: { error?: { code?: string } } })?.error?.error?.code ??
      (err as { error?: { code?: string } })?.error?.code;
    switch (code) {
      case "USER_EMAIL_TAKEN":
        return "Email đã tồn tại trong hệ thống.";
      case "SELF_DISABLE_NOT_ALLOWED":
        return "Không thể vô hiệu hóa chính tài khoản của bạn.";
      case "USER_NOT_FOUND":
        return "Không tìm thấy tài khoản.";
      case "INSUFFICIENT_PERMISSION":
        return "Bạn không có quyền quản trị người dùng.";
      default:
        return fallback;
    }
  }
}
