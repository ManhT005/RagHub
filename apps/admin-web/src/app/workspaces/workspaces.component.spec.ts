import { ComponentFixture, TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { of } from "rxjs";
import { vi } from "vitest";

import { RaghubApiService } from "../core/raghub-api.service";
import { WorkspacesComponent } from "./workspaces.component";

class ApiStub {
  organizations = vi.fn(() =>
    of([{ id: "org-1", name: "RAGHub", slug: "raghub", role: "ADMIN" as const }]),
  );
  workspaces = vi.fn(() =>
    of([
      { id: "ws-1", name: "Tuyển sinh", slug: "tuyen-sinh", organization_id: "org-1" },
      { id: "ws-2", name: "Đào tạo", slug: "dao-tao", organization_id: "org-1" },
    ]),
  );
  documents = vi.fn(() => of([]));
  chatbots = vi.fn(() => of([]));
  createWorkspace = vi.fn();
}

describe("WorkspacesComponent", () => {
  let fixture: ComponentFixture<WorkspacesComponent>;
  let api: ApiStub;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspacesComponent],
      providers: [provideRouter([]), { provide: RaghubApiService, useClass: ApiStub }],
    }).compileComponents();

    fixture = TestBed.createComponent(WorkspacesComponent);
    api = TestBed.inject(RaghubApiService) as unknown as ApiStub;
    fixture.detectChanges();
  });

  it("shows only the workspace list with links to each workspace", () => {
    const text = fixture.nativeElement.textContent;
    const links = fixture.nativeElement.querySelectorAll(
      'a[href^="/app/workspace-console/"]',
    );

    expect(text).toContain("Danh sách workspace");
    expect(text).not.toContain("Quản lý quyền truy cập");
    expect(links.length).toBe(2);
  });

  it("hides the organization picker when there is a single organization", () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).not.toContain("Tổ chức đang quản lý");
    expect(
      fixture.nativeElement.querySelector('[aria-label="Chọn tổ chức"]'),
    ).toBeNull();
  });

  it("shows the organization picker when there are multiple organizations", async () => {
    api.organizations.mockReturnValue(
      of([
        { id: "org-1", name: "RAGHub", slug: "raghub", role: "ADMIN" as const },
        { id: "org-2", name: "Khác", slug: "khac", role: "ADMIN" as const },
      ]),
    );
    (
      fixture.componentInstance as unknown as { loadOrganizations(): void }
    ).loadOrganizations();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain("Tổ chức đang quản lý");
  });
});
