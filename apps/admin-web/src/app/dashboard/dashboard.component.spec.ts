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
              of([{ id: "org-1", name: "Demo", slug: "demo", role: "OWNER" }]),
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

  it("offers quick actions from the overview", async () => {
    const fixture = await setup();
    const content = fixture.nativeElement.textContent;
    expect(content).toContain("Tạo workspace mới");
    expect(content).toContain("Tải tài liệu lên");
    expect(content).toContain("Tạo chatbot");
    expect(content).toContain("Nhúng chatbot");
    expect(
      fixture.nativeElement.querySelector('a[href="/app/workspaces"]'),
    ).not.toBeNull();
  });

  it("renders real counts from the API instead of hardcoded numbers", async () => {
    const fixture = await setup();
    const content = fixture.nativeElement.textContent as string;
    expect(content).not.toContain("1.248");
    expect(content).toContain("Tài liệu a.pdf đã được thêm");
    expect(content).toContain("Chatbot Bot đã được xuất bản");
  });
});
