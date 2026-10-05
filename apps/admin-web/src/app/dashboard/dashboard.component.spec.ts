import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { of } from "rxjs";

import { RaghubApiService } from "../core/raghub-api.service";
import { DashboardComponent } from "./dashboard.component";

describe("DashboardComponent", () => {
  async function setup() {
    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            organizations: () =>
              of([{ id: "org-1", name: "Demo", slug: "demo", role: "ADMIN" }]),
            workspaces: () =>
              of([
                {
                  id: "ws-1",
                  name: "WS1",
                  slug: "ws1",
                  organization_id: "org-1",
                },
                {
                  id: "ws-2",
                  name: "WS2",
                  slug: "ws2",
                  organization_id: "org-1",
                },
              ]),
            documents: (ws: string) =>
              of(
                ws === "ws-1"
                  ? [
                      {
                        id: "d1",
                        name: "a.pdf",
                        status: "READY",
                        created_at: "2026-10-01T01:00:00Z",
                      },
                    ]
                  : [],
              ),
            chatbots: (ws: string) =>
              of(
                ws === "ws-2"
                  ? [
                      {
                        id: "b1",
                        workspace_id: "ws-2",
                        name: "Bot",
                        system_prompt: "",
                        model: null,
                        retrieval_limit: 5,
                        published: true,
                        created_at: "2026-10-01T02:00:00Z",
                      },
                    ]
                  : [],
              ),
          },
        },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  it("hides the quick actions section from the overview", async () => {
    const fixture = await setup();
    const content = fixture.nativeElement.textContent;
    expect(fixture.nativeElement.querySelector(".page-heading")).toBeNull();
    expect(content).not.toContain("Chào mừng trở lại");
    expect(content).not.toContain("Thao tác nhanh");
    expect(content).not.toContain("Tạo workspace mới");
    expect(content).not.toContain("Nhúng chatbot");
    expect(content).toContain("Hoạt động gần đây");
  });

  it("renders real counts from the API instead of hardcoded numbers", async () => {
    const fixture = await setup();
    const content = fixture.nativeElement.textContent as string;
    expect(content).not.toContain("1.248");
    expect(content).toContain("Tài liệu a.pdf đã được thêm");
    expect(content).toContain("Chatbot Bot đã được xuất bản");
  });

  it("renders recent activity as a data table without a surrounding card", async () => {
    const fixture = await setup();
    const headers = fixture.nativeElement.querySelectorAll("thead th");
    const rows = fixture.nativeElement.querySelectorAll("tbody tr.ant-table-row");

    expect(Array.from(headers, (header: Element) => header.textContent?.trim())).toEqual([
      "Loại",
      "Hoạt động",
      "Workspace",
      "Thời gian",
    ]);
    expect(rows.length).toBe(2);
    expect(fixture.nativeElement.querySelector(".activity-card")).toBeNull();
  });

  it("provides workspace and date filters with ten rows per page", async () => {
    const fixture = await setup();
    const component = fixture.componentInstance as unknown as {
      pageSize: number;
      selectedWorkspace: { set(value: string): void };
    };

    expect(fixture.nativeElement.querySelector(".workspace-filter")).not.toBeNull();
    expect(fixture.nativeElement.querySelector(".date-filter")).not.toBeNull();
    expect(component.pageSize).toBe(10);

    component.selectedWorkspace.set("ws-1");
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll("tbody tr.ant-table-row");
    expect(rows.length).toBe(1);
    expect(rows[0].textContent).toContain("a.pdf");
  });
});
