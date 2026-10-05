import { TestBed } from "@angular/core/testing";
import { provideHttpClient } from '@angular/common/http';
import { Router, provideRouter } from "@angular/router";
import {
  DashboardOutline,
  DatabaseOutline,
  FileTextOutline,
  MessageOutline,
  SettingOutline,
  TeamOutline,
} from "@ant-design/icons-angular/icons";
import { provideNzIcons } from "ng-zorro-antd/icon";
import { of } from "rxjs";

import { session } from "../core/api-auth.interceptor";
import { RaghubApiService } from "../core/raghub-api.service";
import { ConsoleLayoutComponent } from "./console-layout.component";
import { WorkspaceContextStore } from '../core/workspace-context/workspace-context.store';
import { workspaceFixture } from '../features/selfhost-test-fixtures';

describe("ConsoleLayoutComponent", () => {
  const currentUser = {
    id: "user-1",
    email: "owner@example.com",
    email_verified: true,
  };

  beforeEach(async () => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    session.accessToken = "test-token";
    await TestBed.configureTestingModule({
      imports: [ConsoleLayoutComponent],
      providers: [
        provideHttpClient(),
        provideRouter([]),
        provideNzIcons([
          DashboardOutline,
          DatabaseOutline,
          FileTextOutline,
          MessageOutline,
          SettingOutline,
          TeamOutline,
        ]),
        {
          provide: RaghubApiService,
          useValue: {
            me: () => of(currentUser),
            organizations: () =>
              of([
                {
                  id: "org-1",
                  name: "RAGHub",
                  slug: "raghub",
                  role: "ADMIN",
                },
              ]),
          },
        },
      ],
    }).compileComponents();
  });

  afterEach(() => {
    session.accessToken = null;
    session.organizationId = null;
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it('isolates workspace navigation and displays its identity and back action', () => {
    const context = TestBed.inject(WorkspaceContextStore);
    context.workspace.set(workspaceFixture);
    context.accessInfo.set({ workspace_id: workspaceFixture.id, is_system_admin: false, permissions: ['workspace.view', 'document.view', 'ai.view', 'member.view'] });
    const fixture = TestBed.createComponent(ConsoleLayoutComponent);
    fixture.detectChanges();
    const sidebar = fixture.nativeElement.querySelector('nz-sider');
    expect(sidebar.querySelector('.workspace-identity').textContent).toContain('Knowledge');
    expect(sidebar.querySelector('.workspace-identity').textContent).toContain('knowledge');
    expect(sidebar.querySelector('.workspace-back').getAttribute('href')).toBe('/app/workspaces');
    expect(sidebar.querySelector('li .workspace-back')).toBeNull();
    expect(sidebar.querySelector('a[href="/app/profile"]')).toBeNull();
    expect(sidebar.querySelector('a[href^="/system"]')).toBeNull();
    expect(sidebar.textContent).toContain('QUẢN TRỊ');
    expect(sidebar.textContent).toContain('AI & Models');
    expect(sidebar.querySelector('a[href$="/chat"]')).toBeNull();
  });

  it('hides the administration group for document-only members and keeps global account access', () => {
    const context = TestBed.inject(WorkspaceContextStore);
    context.workspace.set(workspaceFixture);
    context.accessInfo.set({ workspace_id: workspaceFixture.id, is_system_admin: false, permissions: ['workspace.view', 'document.view'] });
    const fixture = TestBed.createComponent(ConsoleLayoutComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.workspace-admin-label')).toBeNull();
    context.clear();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('nz-sider a[href="/app/profile"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.workspace-identity')).toBeNull();
  });

  it("shows the signed-in user email in the account trigger", () => {
    const fixture = TestBed.createComponent(ConsoleLayoutComponent);
    fixture.detectChanges();

    const trigger = fixture.nativeElement.querySelector(
      ".topbar .account-trigger",
    );
    expect(trigger).not.toBeNull();
    expect(trigger?.textContent).toContain("owner@example.com");
    expect(trigger?.getAttribute("aria-expanded")).toBe("false");
    expect(fixture.nativeElement.querySelector("footer .account-trigger")).toBeNull();
  });

  it("shows the brand in the topbar and removes it from the sidebar", () => {
    const fixture = TestBed.createComponent(ConsoleLayoutComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector(".topbar .topbar-brand")).not.toBeNull();
    expect(fixture.nativeElement.querySelector("nz-sider .brand")).toBeNull();
  });

  it("removes the sidebar heading and toggles the collapsed sidebar", () => {
    const fixture = TestBed.createComponent(ConsoleLayoutComponent);
    fixture.detectChanges();

    const shell = fixture.nativeElement.querySelector(".console-shell");
    const toggle = fixture.nativeElement.querySelector(
      ".sidebar-toggle",
    ) as HTMLButtonElement;

    expect(fixture.nativeElement.querySelector(".nav-label")).toBeNull();
    expect(shell.classList.contains("sidebar-collapsed")).toBe(false);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");

    toggle.click();
    fixture.detectChanges();

    expect(shell.classList.contains("sidebar-collapsed")).toBe(true);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.getAttribute("aria-label")).toBe("Mở sidebar");
  });

  it("opens an account menu with profile, password, and logout actions", () => {
    const fixture = TestBed.createComponent(ConsoleLayoutComponent);
    fixture.detectChanges();

    const trigger = fixture.nativeElement.querySelector(
      ".topbar .account-trigger",
    ) as HTMLButtonElement | null;
    trigger?.click();
    fixture.detectChanges();

    const menu = fixture.nativeElement.querySelector(".account-menu");
    expect(menu).not.toBeNull();
    expect(menu?.textContent).toContain("Tài khoản");
    expect(menu?.textContent).toContain("Đổi mật khẩu");
    expect(menu?.textContent).toContain("Đăng xuất");
    expect(trigger?.getAttribute("aria-expanded")).toBe("true");
  });

  it("clears the session and returns to login when logging out", () => {
    const fixture = TestBed.createComponent(ConsoleLayoutComponent);
    const router = TestBed.inject(Router);
    const navigateSpy = vi
      .spyOn(router, "navigateByUrl")
      .mockResolvedValue(true);
    fixture.detectChanges();

    const trigger = fixture.nativeElement.querySelector(
      ".topbar .account-trigger",
    ) as HTMLButtonElement | null;
    trigger?.click();
    fixture.detectChanges();
    const logout = fixture.nativeElement.querySelector(
      ".account-menu__logout",
    ) as HTMLButtonElement | null;
    logout?.click();

    expect(session.accessToken).toBeNull();
    expect(session.organizationId).toBeNull();
    expect(navigateSpy).toHaveBeenCalledWith("/auth");
  });
  it("toggles the admin theme and persists the selected mode", () => {
    const fixture = TestBed.createComponent(ConsoleLayoutComponent);
    fixture.detectChanges();

    const toggle = fixture.nativeElement.querySelector(
      ".theme-toggle",
    ) as HTMLButtonElement | null;
    expect(toggle).not.toBeNull();
    expect(document.documentElement.dataset["theme"]).toBe("light");

    toggle?.click();
    fixture.detectChanges();

    expect(document.documentElement.dataset["theme"]).toBe("dark");
    expect(localStorage.getItem("raghub-theme")).toBe("dark");
    expect(toggle?.getAttribute("aria-pressed")).toBe("true");
  });
  it("hides security from the sidebar while keeping it in the account menu", () => {
    const fixture = TestBed.createComponent(ConsoleLayoutComponent);
    fixture.detectChanges();

    expect(
      fixture.nativeElement.querySelector('ul a[href="/app/security"]'),
    ).toBeNull();

    fixture.nativeElement.querySelector(".topbar .account-trigger")?.click();
    fixture.detectChanges();

    expect(
      fixture.nativeElement.querySelector('.account-menu a[href="/app/security"]'),
    ).not.toBeNull();
  });
});
