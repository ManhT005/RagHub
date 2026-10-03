import { ComponentFixture, TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { of, throwError } from "rxjs";
import { vi } from "vitest";

import { RaghubApiService } from "../core/raghub-api.service";
import { UsersComponent } from "./users.component";

const organizations = [
  { id: "org-1", name: "RAGHub", slug: "raghub", role: "ADMIN" as const },
];

const page = {
  items: [
    {
      id: "user-1",
      email: "lan@example.com",
      display_name: "Lan Nguyen",
      status: "ACTIVE",
      last_login_at: null,
      created_at: "2026-10-01T00:00:00Z",
      role: "WORKSPACE_ADMIN" as const,
      workspace_ids: ["ws-1"],
      workspaces: [{ id: "ws-1", name: "Tuyển sinh", slug: "tuyen-sinh" }],
    },
  ],
  page: 1,
  page_size: 10,
  total: 1,
};

class ApiStub {
  organizations = vi.fn(() => of(organizations));
  adminUsers = vi.fn(() => of(page));
  createAdminUser = vi.fn(() => of(page.items[0]));
  updateAdminUser = vi.fn((id: string, displayName: string | null) =>
    of({ ...page.items[0], display_name: displayName }),
  );
  updateAdminUserStatus = vi.fn(() =>
    of({ ...page.items[0], status: "DISABLED" }),
  );
}

describe("UsersComponent", () => {
  let fixture: ComponentFixture<UsersComponent>;
  let api: ApiStub;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [UsersComponent],
      providers: [
        provideRouter([]),
        { provide: RaghubApiService, useClass: ApiStub },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(UsersComponent);
    api = TestBed.inject(RaghubApiService) as unknown as ApiStub;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it("requests ten users per page and renders Vietnamese content", () => {
    expect(api.adminUsers).toHaveBeenCalledWith("", 1, 10);
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain("Quản lý người dùng");
    expect(text).toContain("Lan Nguyen");
    expect(text).toContain("lan@example.com");
    expect(text).toContain("Tuyển sinh");
    expect(text).toContain("Tạo tài khoản");
    expect(text).toContain("Đổi tên");
    expect(text).toContain("Vô hiệu hóa");
    expect(text).not.toMatch(/[一-鿿]/);
  });

  it("renders user actions as solid primary and danger buttons", () => {
    const buttons = fixture.nativeElement.querySelectorAll(".actions button");

    expect(buttons.length).toBe(2);
    expect(buttons[0].classList.contains("ant-btn-primary")).toBe(true);
    expect(buttons[1].classList.contains("ant-btn-primary")).toBe(true);
    expect(buttons[1].classList.contains("ant-btn-dangerous")).toBe(true);
  });

  it("uses debounced search without a submit button and keeps create action large", () => {
    const toolbar = fixture.nativeElement.querySelector(".toolbar") as HTMLElement;
    const createButton = Array.from(
      toolbar.querySelectorAll("button"),
    ).find((button) => button.textContent?.includes("Tạo tài khoản"));

    expect(toolbar.textContent).not.toContain("Tìm kiếm");
    expect(createButton?.classList.contains("ant-btn-lg")).toBe(true);
  });

  it("places the user table on a white table panel", () => {
    const panel = fixture.nativeElement.querySelector(".table-panel");

    expect(panel).not.toBeNull();
    expect(panel.querySelector("nz-table")).not.toBeNull();
  });

  it("hides the organization picker for a single organization", () => {
    expect(fixture.nativeElement.textContent).not.toContain(
      "Tổ chức đang quản lý",
    );
  });

  it("shows the organization picker for multiple organizations", async () => {
    api.organizations.mockReturnValue(
      of([
        ...organizations,
        { id: "org-2", name: "Khác", slug: "khac", role: "ADMIN" as const },
      ]),
    );
    (
      fixture.componentInstance as unknown as { loadOrganizations(): void }
    ).loadOrganizations();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain(
      "Tổ chức đang quản lý",
    );
  });

  it("shows a Vietnamese empty state when no user matches", async () => {
    api.adminUsers.mockReturnValueOnce(
      of({ items: [], page: 1, page_size: 10, total: 0 }),
    );
    (fixture.componentInstance as unknown as { search(): void }).search();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain(
      "Chưa có người dùng phù hợp",
    );
  });

  it("renames a user through the rename dialog", async () => {
    const component = fixture.componentInstance as unknown as {
      openRename(u: unknown): void;
      renameValue: { set(v: string): void };
      rename(): void;
    };
    component.openRename(page.items[0]);
    fixture.detectChanges();
    component.renameValue.set("Lan Tran");
    component.rename();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(api.updateAdminUser).toHaveBeenCalledWith("user-1", "Lan Tran");
    expect(fixture.nativeElement.textContent).toContain(
      "Đã cập nhật tên hiển thị.",
    );
  });

  it("keeps table data and shows Vietnamese message when status change fails", async () => {
    api.updateAdminUserStatus.mockReturnValueOnce(
      throwError(() => ({
        error: { error: { code: "SELF_DISABLE_NOT_ALLOWED" } },
      })),
    );
    const toggle = (
      fixture.componentInstance as unknown as { toggleStatus(u: unknown): void }
    ).toggleStatus.bind(fixture.componentInstance);
    toggle(page.items[0]);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain(
      "Không thể vô hiệu hóa chính tài khoản của bạn.",
    );
    expect(fixture.nativeElement.textContent).toContain("lan@example.com");
  });
});
