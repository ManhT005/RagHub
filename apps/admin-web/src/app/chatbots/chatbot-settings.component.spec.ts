import { TestBed } from "@angular/core/testing";
import { provideNoopAnimations } from "@angular/platform-browser/animations";
import { ActivatedRoute, convertToParamMap, provideRouter } from "@angular/router";
import { of, Subject } from "rxjs";
import { vi } from "vitest";
import { ChatbotSettingsComponent } from "./chatbot-settings.component";
import { RaghubApiService } from "../core/raghub-api.service";
import { parseWidgetOrigins, widgetForeground } from "./widget-settings.utils";

const bot = {
  id: "bot-1", name: "Trợ lý tài liệu", workspace_id: "ws-1", system_prompt: "",
  model: null, retrieval_limit: 5, published: true, allowed_origins: ["https://example.com"],
  embed_primary_color: "#8faaf6", embed_title: "Trợ lý", embed_greeting: "Xin chào!",
  created_at: "", updated_at: null,
};
const metadata = { code: null, key: null, public_base_url: "http://127.0.0.1:8080", script_src: "http://127.0.0.1:8080/widget/raghub.js", has_embed_key: true };
const issued = { ...metadata, key: "rgh_new", code: '<script src="http://127.0.0.1:8080/widget/raghub.js" data-chatbot-key="rgh_new" async></script>' };

describe("widget settings", () => {
  async function setup(overrides = {}) {
    const api = { chatbot: vi.fn(() => of(bot)), embedCode: vi.fn(() => of(metadata)),
      publishEmbed: vi.fn(() => of(issued)), rotateEmbedKey: vi.fn(() => of(issued)), ...overrides };
    await TestBed.configureTestingModule({ imports: [ChatbotSettingsComponent], providers: [
      provideRouter([]), provideNoopAnimations(), { provide: RaghubApiService, useValue: api },
      { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ id: bot.id }) } } },
    ] }).compileComponents();
    const fixture = TestBed.createComponent(ChatbotSettingsComponent);
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, api, element: fixture.nativeElement as HTMLElement };
  }
  it("shows public URL and explains show-once keys without enabling copy on reload", async () => {
    const { element, component } = await setup();
    expect(element.textContent).toContain("key cũ không được hiển thị lại");
    expect(element.textContent).toContain("chính máy đang chạy RagHub");
    expect(element.querySelector('pre')).toBeNull();
    expect((element.querySelector('.embed-actions button') as HTMLButtonElement).disabled).toBe(true);
    expect(component.demoUrl()).toBeNull();
  });
  it("syncs hex/swatch, validates input and previews safe contrast without public chat requests", async () => {
    const { fixture, component, element, api } = await setup();
    const hex = element.querySelector('.color-hex') as HTMLInputElement;
    hex.value = "#ffffff"; hex.dispatchEvent(new Event('input'));
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
    expect(component.primaryColor).toBe("#ffffff");
    expect(component.previewForeground()).toBe("#000000");
    expect((element.querySelector('.color-swatch') as HTMLInputElement).value).toBe("#ffffff");
    const swatch = element.querySelector('.color-swatch') as HTMLInputElement;
    swatch.value = "#123456"; swatch.dispatchEvent(new Event('input'));
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
    expect(hex.value).toBe("#123456");
    hex.value = "bad"; hex.dispatchEvent(new Event('input'));
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
    component.publish();
    expect(api.publishEmbed).not.toHaveBeenCalled();
    expect((element.querySelector('.form-actions button') as HTMLButtonElement).disabled).toBe(true);
  });
  it("normalizes allowed origins and rejects paths before submission", async () => {
    const { component, api } = await setup();
    component.origins = "https://example.com/page.html";
    component.publish(); expect(api.publishEmbed).not.toHaveBeenCalled();
    component.origins = "HTTPS://Example.COM:443/\nhttps://example.com";
    component.publish();
    expect(api.publishEmbed).toHaveBeenCalledWith(bot.id, expect.objectContaining({ allowed_origins: ["https://example.com"] }));
    expect(component.demoUrl()).toContain('#key=rgh_new');
    expect(new URL(component.demoUrl()!).search).toBe("");
  });
  it("retains the show-once code after saving settings with an existing key", async () => {
    const publish = vi.fn().mockReturnValueOnce(of(issued)).mockReturnValueOnce(of(metadata));
    const { component } = await setup({ publishEmbed: publish });
    component.publish(); component.title = "Tiêu đề mới"; component.publish();
    expect(component.code()).toBe(issued.code);
    expect(component.notice()).toContain("vẫn hoạt động");
  });
  it("blocks duplicate writes while publish is pending", async () => {
    const pending = new Subject<any>();
    const { component, api } = await setup({ publishEmbed: vi.fn(() => pending) });
    component.publish(); component.publish(); component.rotate();
    expect(api.publishEmbed).toHaveBeenCalledTimes(1);
    expect(api.rotateEmbedKey).not.toHaveBeenCalled();
    pending.next(issued); pending.complete();
    expect(component.busy()).toBe(false);
  });
  it("does not let a delayed metadata read clear a newly issued key", async () => {
    const delayed = new Subject<any>();
    const { component } = await setup({ embedCode: vi.fn(() => delayed) });
    component.publish();
    delayed.next(metadata); delayed.complete();
    expect(component.code()).toBe(issued.code);
    expect(component.rawKey()).toBe("rgh_new");
  });
  it("reports clipboard failure without claiming success", async () => {
    const { component } = await setup();
    component.publish();
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn(() => Promise.reject(new Error())) } });
    await component.copy();
    expect(component.error()).toContain("Không thể sao chép");
    expect(component.notice()).not.toContain("Đã sao chép");
  });
});

describe("origin and contrast helpers", () => {
  it("rejects credentials, wildcards, queries and non-http URLs", () => {
    for (const origin of ["https://u:p@host", "https://*.example.com", "https://host?", "https://host#", "file://host", "https://host\\evil", "http://host:0"]) expect(parseWidgetOrigins(origin).error).not.toBe("");
  });
  it("provides AA foreground contrast for light and dark colors", () => {
    expect(widgetForeground("#ffffff")).toBe("#000000");
    expect(widgetForeground("#000000")).toBe("#ffffff");
    expect(widgetForeground("#8faaf6")).toBe("#000000");
  });
});
