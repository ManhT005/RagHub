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

import { session } from "../core/api-auth.interceptor";
import { consoleOrganization } from "../core/console-organization";
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
  protected readonly accountMenuOpen = signal(false);
  protected readonly sidebarCollapsed = signal(false);
  protected readonly darkMode = signal(false);
  protected readonly userLabel = computed(
    () => this.user()?.email ?? "Đang tải tài khoản…",
  );
  protected readonly userInitial = computed(
    () => this.user()?.email.slice(0, 1).toUpperCase() ?? "T",
  );

  private readonly api = inject(RaghubApiService);
  private readonly router = inject(Router);

  constructor() {
    const storedTheme = localStorage.getItem("raghub-theme");
    const prefersDark =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    this.darkMode.set(storedTheme ? storedTheme === "dark" : prefersDark);
    this.applyTheme();
    this.api.organizations().subscribe({
      next: (organizations) => this.organizations.set(organizations),
      error: () => this.organizations.set([]),
    });
    this.api.me().subscribe({
      next: (user) => this.user.set(user),
      error: () => this.logout(),
    });
  }

  protected toggleTheme(): void {
    this.darkMode.update((isDark) => !isDark);
    localStorage.setItem("raghub-theme", this.darkMode() ? "dark" : "light");
    this.applyTheme();
  }

  private applyTheme(): void {
    document.documentElement.dataset["theme"] = this.darkMode()
      ? "dark"
      : "light";
  }

  protected toggleAccountMenu(): void {
    this.accountMenuOpen.update((isOpen) => !isOpen);
  }

  protected closeAccountMenu(): void {
    this.accountMenuOpen.set(false);
  }

  protected logout(): void {
    this.closeAccountMenu();
    session.accessToken = null;
    session.organizationId = null;
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
