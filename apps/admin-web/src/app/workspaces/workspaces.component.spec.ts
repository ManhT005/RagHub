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
  members = vi.fn(() => of([]));
  saveMember = vi.fn();
  deleteMember = vi.fn();
  createWorkspace = vi.fn(() =>
    of({
      id: "ws-3",
      name: "Tư vấn tuyển sinh",
      slug: "tu-van-tuyen-sinh",
      organization_id: "org-1",
    }),
  );
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

  it("shows workspace actions for access, documents and chatbots", () => {
    const text = fixture.nativeElement.textContent;
    const documentLinks = fixture.nativeElement.querySelectorAll(
      'a[href^="/app/documents?workspaceId="]',
    );
    const chatbotLinks = fixture.nativeElement.querySelectorAll(
      'a[href^="/app/chatbots?workspaceId="]',
    );

    expect(text).toContain("Danh sách workspace");
    expect(text).not.toContain("Quản lý quyền truy cập");
    expect(fixture.nativeElement.querySelector(".create-workspace")).toBeNull();
    expect(documentLinks.length).toBe(2);
    expect(chatbotLinks.length).toBe(2);
    expect(
      fixture.nativeElement.querySelectorAll(".workspace-access-action").length,
    ).toBe(2);
  });

  it("renders every workspace as one row in a data table", () => {
    const headers = fixture.nativeElement.querySelectorAll("thead th");
    const rows = fixture.nativeElement.querySelectorAll("tbody tr.ant-table-row");

    expect(Array.from(headers, (header: Element) => header.textContent?.trim())).toEqual([
      "Workspace",
      "Mã định danh",
      "Tài liệu",
      "Chatbot",
      "Thao tác",
    ]);
    expect(rows.length).toBe(2);
    expect(fixture.nativeElement.querySelector(".workspace-card")).toBeNull();
    expect(rows[0].querySelector(".workspace-documents-link")).not.toBeNull();
    expect(rows[0].querySelector(".workspace-chatbots-link")).not.toBeNull();
  });

  it("renders the chatbot action as a solid primary button", () => {
    const action = fixture.nativeElement.querySelector(".workspace-chatbots-link");

    expect(action.classList.contains("ant-btn-primary")).toBe(true);
  });

  it("opens the existing workspace access UI from a row action", () => {
    const accessButton = fixture.nativeElement.querySelector(
      ".workspace-access-action",
    ) as HTMLButtonElement;

    accessButton.click();
    fixture.detectChanges();

    const modal = document.body.querySelector(".workspace-access-modal");
    expect(modal).not.toBeNull();
    expect(modal?.textContent).toContain("PHÂN QUYỀN WORKSPACE");
    expect(modal?.textContent).toContain("Tuyển sinh");
    expect(api.members).toHaveBeenCalledWith("org-1");
  });

  it("filters without a submit button and keeps the create action large", () => {
    const toolbar = fixture.nativeElement.querySelector(
      ".workspaces-page > .toolbar",
    ) as HTMLElement | null;
    const createButton = toolbar?.querySelector(
      ".add-space-button",
    ) as HTMLButtonElement | null;

    expect(toolbar).not.toBeNull();
    expect(toolbar?.textContent).not.toContain("Tìm kiếm");
    expect(createButton?.classList.contains("ant-btn-lg")).toBe(true);
  });
  it("hides the organization picker when there is a single organization", () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).not.toContain("Tổ chức đang quản lý");
    expect(
      fixture.nativeElement.querySelector('[aria-label="Chọn tổ chức"]'),
    ).toBeNull();
  });

  it("places the workspace table on a white table panel", () => {
    const panel = fixture.nativeElement.querySelector(".table-panel");

    expect(panel).not.toBeNull();
    expect(panel.querySelector("nz-table")).not.toBeNull();
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

  it("keeps the create modal hidden until an admin chooses to create a workspace", () => {
    const addButton = fixture.nativeElement.querySelector(
      ".add-space-button",
    ) as HTMLButtonElement;

    expect(document.body.querySelector(".create-workspace-modal")).toBeNull();
    expect(addButton.textContent).toContain("Tạo workspace");
    expect(addButton.textContent).not.toContain("Thêm space");
    expect(addButton.getAttribute("aria-expanded")).toBe("false");

    addButton.click();
    fixture.detectChanges();

    const createModal = document.body.querySelector(".create-workspace-modal");
    expect(createModal).not.toBeNull();
    expect(createModal?.textContent).toContain("Tạo workspace mới");
    expect(addButton.getAttribute("aria-expanded")).toBe("true");
  });

  it("clears and closes the create modal when cancelled", () => {
    fixture.nativeElement.querySelector(".add-space-button").click();
    fixture.detectChanges();

    const nameInput = document.body.querySelector(
      'input[name="name"]',
    ) as HTMLInputElement;
    nameInput.value = "Bản nháp";
    nameInput.dispatchEvent(new Event("input"));
    document.body.querySelector<HTMLButtonElement>(
      ".create-workspace-modal .ant-modal-footer button:first-of-type",
    )?.click();
    fixture.detectChanges();

    expect(
      fixture.nativeElement.querySelector(".add-space-button").getAttribute("aria-expanded"),
    ).toBe("false");
    expect((fixture.componentInstance as unknown as { name: string }).name).toBe("");
  });

  it("creates a workspace and closes the modal after success", () => {
    fixture.nativeElement.querySelector(".add-space-button").click();
    fixture.detectChanges();
    const component = fixture.componentInstance as unknown as { name: string };
    component.name = "Tư vấn tuyển sinh";

    (fixture.componentInstance as unknown as { create(): void }).create();
    fixture.detectChanges();

    expect(api.createWorkspace).toHaveBeenCalledWith(
      "Tư vấn tuyển sinh",
      "tu-van-tuyen-sinh",
    );
    expect(
      fixture.nativeElement.querySelector(".add-space-button").getAttribute("aria-expanded"),
    ).toBe("false");
    expect(
      fixture.nativeElement.querySelectorAll("tbody tr.ant-table-row").length,
    ).toBe(3);
  });
});
