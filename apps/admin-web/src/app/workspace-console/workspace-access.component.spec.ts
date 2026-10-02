import { ComponentFixture, TestBed } from "@angular/core/testing";
import { of } from "rxjs";
import { vi } from "vitest";

import { RaghubApiService } from "../core/raghub-api.service";
import { WorkspaceAccessComponent } from "./workspace-access.component";

class ApiStub {
  members = vi.fn(() =>
    of([
      {
        user_id: "user-1",
        email: "lan@example.com",
        role: "WORKSPACE_ADMIN" as const,
        workspace_ids: ["ws-1", "ws-2"],
      },
    ]),
  );
  saveMember = vi.fn((_orgId, email, role, workspaceIds) =>
    of({
      user_id: "user-1",
      email,
      role,
      workspace_ids: workspaceIds,
    }),
  );
  deleteMember = vi.fn(() => of(void 0));
}

describe("WorkspaceAccessComponent", () => {
  let fixture: ComponentFixture<WorkspaceAccessComponent>;
  let api: ApiStub;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceAccessComponent],
      providers: [{ provide: RaghubApiService, useClass: ApiStub }],
    }).compileComponents();

    fixture = TestBed.createComponent(WorkspaceAccessComponent);
    fixture.componentRef.setInput("organizationId", "org-1");
    fixture.componentRef.setInput("workspaceId", "ws-1");
    fixture.componentRef.setInput("workspaceName", "Tuyển sinh");
    fixture.componentRef.setInput("isAdmin", true);
    api = TestBed.inject(RaghubApiService) as unknown as ApiStub;
    fixture.detectChanges();
  });

  it("lists only administrators assigned to the current workspace", () => {
    expect(fixture.nativeElement.textContent).toContain("lan@example.com");
    expect(fixture.nativeElement.textContent).toContain("Tuyển sinh");
  });

  it("preserves other workspace assignments when adding an existing administrator", () => {
    const component = fixture.componentInstance as any;
    component.email = "lan@example.com";

    component.addAdmin();

    expect(api.saveMember).toHaveBeenCalledWith(
      "org-1",
      "lan@example.com",
      "WORKSPACE_ADMIN",
      ["ws-1", "ws-2"],
    );
  });

  it("removes only the current workspace assignment", () => {
    const component = fixture.componentInstance as any;
    component.removeAdmin(component.workspaceAdmins()[0]);

    expect(api.saveMember).toHaveBeenCalledWith(
      "org-1",
      "lan@example.com",
      "WORKSPACE_ADMIN",
      ["ws-2"],
    );
    expect(api.deleteMember).not.toHaveBeenCalled();
  });
});
