import { TestBed } from "@angular/core/testing";
import { signal } from "@angular/core";
import { of } from "rxjs";
import { SetupStateService } from "../setup/setup-state.service";
import { provideRouter } from "@angular/router";
import { RouterTestingHarness } from "@angular/router/testing";
import { routes } from "../app.routes";

describe("Public pages", () => {
  beforeEach(() =>
    TestBed.configureTestingModule({ providers: [provideRouter(routes), { provide: SetupStateService, useValue: { status: () => of({ initialized: true }), unavailable: signal(false) } }] }),
  );

  it("links home navigation to separate public pages", async () => {
    const harness = await RouterTestingHarness.create("/");
    const element = harness.routeNativeElement!;
    expect(
      Array.from(element.querySelectorAll(".nav-links a")).map((a) =>
        a.getAttribute("href"),
      ),
    ).toEqual(["/", "/tinh-nang", "/giai-phap", "/huong-dan", "/lien-he"]);
    expect(
      element.querySelector(".hero-actions a:last-child")?.getAttribute("href"),
    ).toBe("/tinh-nang");
  });

  it("provides task-based guidance for every RagHub audience", async () => {
    const harness = await RouterTestingHarness.create("/huong-dan");
    const element = harness.routeNativeElement!;
    expect(element.querySelector("h1")?.textContent).toContain("Hướng dẫn");
    expect(element.querySelectorAll(".persona-guides article").length).toBe(5);
    expect(element.textContent).toContain("Quản trị hệ thống");
    expect(element.textContent).toContain("Người quản lý nội dung");
    expect(element.textContent).toContain("Người tra cứu");
    expect(element.textContent).toContain("Đội tích hợp website");
    expect(element.querySelector('a[href="/lien-he"]')).not.toBeNull();
  });

  it("renders features with planned embedding clearly labeled", async () => {
    const harness = await RouterTestingHarness.create("/tinh-nang");
    expect(
      harness.routeNativeElement!.querySelector("h1")?.textContent,
    ).toContain("Tính năng");
    expect(harness.routeNativeElement!.textContent).toContain(
      "Phát hành chatbot",
    );
    expect(harness.routeNativeElement!.textContent).toContain(
      "nguồn tham chiếu",
    );
  });

  it("renders solutions and updates content when navigating to contact", async () => {
    const harness = await RouterTestingHarness.create("/giai-phap");
    expect(
      harness.routeNativeElement!.querySelector("h1")?.textContent,
    ).toContain("Giải pháp");
    expect(harness.routeNativeElement!.textContent).toContain("Trường học");
    await harness.navigateByUrl("/lien-he");
    expect(
      harness.routeNativeElement!.querySelector("h1")?.textContent,
    ).toContain("Liên hệ");
  });

  it("uses actual team contact details without a fake submission form", async () => {
    const harness = await RouterTestingHarness.create("/lien-he");
    const element = harness.routeNativeElement!;
    expect(element.textContent).toContain("DoubleT");
    expect(element.textContent).toContain("Đồng Văn Tú");
    expect(
      element.querySelector('a[href="mailto:khactu731@gmail.com"]'),
    ).not.toBeNull();
    expect(element.querySelector('a[href^="tel:"]')).toBeNull();
    expect(element.querySelector("form")).toBeNull();
    expect(element.querySelector('a[aria-current="page"]')?.textContent).toBe(
      "Liên hệ",
    );
  });
});
