import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { provideNoopAnimations } from "@angular/platform-browser/animations";
import { of } from "rxjs";
import { WorkspaceApiService } from "../../core/api/workspace-api.service";
import { ProviderApiService } from "../../core/api/provider-api.service";
import { RaghubApiService, Organization } from "../../core/raghub-api.service";
import { session } from "../../core/api-auth.interceptor";
import { workspaceFixture } from "../selfhost-test-fixtures";
import { WorkspacesPageComponent } from "./workspaces-page.component";
describe("Workspace aggregate list", () => {
  const api = {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    changeEmbedding: vi.fn(),
    remove: vi.fn(),
  };
  const providers = { models: vi.fn() };
  const documents = vi.fn();
  let organizations: Organization[];
  beforeEach(async () => {
    vi.clearAllMocks();
    session.organizationId = "org-1";
    organizations = [
      { id: "org-1", name: "RagHub", slug: "raghub", role: "WORKSPACE_ADMIN" },
    ];
    providers.models.mockReturnValue(of([]));
    api.create.mockReturnValue(of(workspaceFixture));
    api.remove.mockReturnValue(of(null));
    api.list.mockReturnValue(
      of(
        Array.from({ length: 12 }, (_, i) => ({
          ...workspaceFixture,
          id: `workspace-${i}`,
        })),
      ),
    );
    await TestBed.configureTestingModule({
      imports: [WorkspacesPageComponent],
      providers: [
        provideRouter([]),
        provideNoopAnimations(),
        { provide: WorkspaceApiService, useValue: api },
        { provide: ProviderApiService, useValue: providers },
        {
          provide: RaghubApiService,
          useValue: { organizations: () => of(organizations), documents },
        },
      ],
    }).compileComponents();
  });
  afterEach(() => {
    session.organizationId = null;
  });
  it("uses one summary request regardless of workspace count", () => {
    const view = TestBed.createComponent(WorkspacesPageComponent);
    view.detectChanges();
    expect(api.list).toHaveBeenCalledTimes(1);
    expect(documents).not.toHaveBeenCalled();
    expect(providers.models).not.toHaveBeenCalled();
    expect(view.nativeElement.textContent).toContain("current-model");
    view.destroy();
  });
  it("hides system-only creation from a delegated member", () => {
    const view = TestBed.createComponent(WorkspacesPageComponent);
    view.detectChanges();
    expect(view.nativeElement.textContent).not.toContain("+ Tạo workspace");
    view.componentInstance["open"]();
    view.componentInstance["name"] = "Forbidden";
    view.componentInstance["save"]();
    view.componentInstance["remove"](workspaceFixture);
    expect(api.create).not.toHaveBeenCalled();
    expect(api.remove).not.toHaveBeenCalled();
    view.destroy();
  });
  it("exposes workspace creation and deletion to the system admin without a domain selector", () => {
    organizations[0].role = "ADMIN";
    organizations.push({
      id: "other",
      name: "Other test",
      slug: "other",
      role: "ADMIN",
    });
    const view = TestBed.createComponent(WorkspacesPageComponent);
    view.detectChanges();
    expect(
      view.nativeElement.querySelector('[aria-label="Chọn tổ chức"]'),
    ).toBeNull();
    expect(view.nativeElement.textContent).toContain("+ Tạo workspace");
    const component = view.componentInstance;
    component["open"]();
    component["name"] = "New workspace";
    component["slug"] = "new-workspace";
    component["save"]();
    expect(api.create).toHaveBeenCalledWith("New workspace", "new-workspace");
    component["remove"](workspaceFixture);
    expect(api.remove).toHaveBeenCalledWith(workspaceFixture.id);
    expect(session.organizationId).toBe("org-1");
    view.destroy();
  });
  it("starts in the installation scope rather than the first unrelated test domain", () => {
    session.organizationId = null;
    organizations.unshift({
      id: "test",
      name: "Test",
      slug: "test",
      role: "ADMIN",
    });
    const view = TestBed.createComponent(WorkspacesPageComponent);
    view.detectChanges();
    expect(session.organizationId).toBe("org-1");
    expect(view.nativeElement.textContent).not.toContain("+ Tạo workspace");
    expect(providers.models).not.toHaveBeenCalled();
    view.destroy();
  });
});
