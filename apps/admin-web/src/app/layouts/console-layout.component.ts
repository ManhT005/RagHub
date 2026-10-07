import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  computed,
  inject,
  signal,
} from "@angular/core";
import {
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from "@angular/router";
import { CloudServerOutline } from "@ant-design/icons-angular/icons";
import { provideNzIconsPatch } from "ng-zorro-antd/icon";
import { NzIconModule } from "ng-zorro-antd/icon";
import { NzLayoutModule } from "ng-zorro-antd/layout";
import { NzMenuModule } from "ng-zorro-antd/menu";

import { HttpErrorResponse } from "@angular/common/http";
import { AuthSessionService } from "../core/auth-session.service";
import { consoleOrganization } from "../core/console-organization";
import { ThemeService } from "../core/theme.service";
import { WorkspaceContextStore } from "../core/workspace-context/workspace-context.store";
import {
  type Organization,
  type CurrentUser,
  RaghubApiService,
} from "../core/raghub-api.service";

@Component({
  selector: "raghub-console-layout",
  imports: [
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    NzIconModule,
    NzLayoutModule,
    NzMenuModule,
  ],
  providers: [provideNzIconsPatch([CloudServerOutline])],
  templateUrl: "./console-layout.component.html",
  styleUrl: "./console-layout.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ConsoleLayoutComponent {
  protected readonly context = inject(WorkspaceContextStore);
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly isAdmin = computed(() => {
    const current = consoleOrganization(this.organizations());
    return current?.role === "ADMIN";
  });

  protected readonly user = signal<CurrentUser | null>(null);
  protected readonly accountError = signal("");
  protected readonly accountMenuOpen = signal(false);
  protected readonly sidebarCollapsed = signal(false);
  private readonly theme = inject(ThemeService);
  protected readonly darkMode = this.theme.darkMode;
  protected readonly userLabel = computed(
    () => this.user()?.email ?? "Đang tải tài khoản…",
  );
  protected readonly userInitial = computed(
    () => this.user()?.email.slice(0, 1).toUpperCase() ?? "T",
  );

  private readonly api = inject(RaghubApiService);
  private readonly auth = inject(AuthSessionService);
  private readonly router = inject(Router);

  constructor() {
    this.api.organizations().subscribe({
      next: (organizations) => this.organizations.set(organizations),
      error: () => this.organizations.set([]),
    });
    this.loadAccount();
  }

  protected loadAccount(): void {
    this.accountError.set("");
    this.api.me().subscribe({
      next: (user) => this.user.set(user),
      error: (error) => {
        if (error instanceof HttpErrorResponse && error.status === 401) {
          this.auth.clearLocalSession();
          void this.router.navigateByUrl("/auth");
        } else {
          this.accountError.set(error.status === 403 ? "Tài khoản không có quyền truy cập." : "Kết nối tạm thời gián đoạn. Vui lòng thử lại.");
        }
      },
    });
  }

  protected toggleTheme(): void {
    this.theme.toggleTheme();
  }

  protected toggleAccountMenu(): void {
    this.accountMenuOpen.update((isOpen) => !isOpen);
  }

  protected closeAccountMenu(): void {
    this.accountMenuOpen.set(false);
  }

  protected logout(): void {
    this.closeAccountMenu();
    this.auth.logout().subscribe();
    void this.router.navigateByUrl("/auth");
  }

  @HostListener("document:click")
  @HostListener("document:keydown.escape")
  protected closeAccountMenuFromDocument(): void {
    this.closeAccountMenu();
  }

  protected toggleSidebar(): void {
    this.sidebarCollapsed.update((isCollapsed) => !isCollapsed);
  }
}
