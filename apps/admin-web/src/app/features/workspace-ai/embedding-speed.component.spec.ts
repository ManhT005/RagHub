import { TestBed } from "@angular/core/testing";
import { provideNoopAnimations } from "@angular/platform-browser/animations";
import { of, Subject } from "rxjs";
import { WorkspaceApiService } from "../../core/api/workspace-api.service";
import { WorkspaceContextStore } from "../../core/workspace-context/workspace-context.store";
import { contextFixture } from "../selfhost-test-fixtures";
import { EmbeddingSpeedComponent } from "./embedding-speed.component";

describe("Embedding speed settings", () => {
  const runtime = { profile: "balanced", preference: {}, effective_max_inflight: 2,
    effective_batch_chunks: 32, effective_batch_tokens: 20000, limited_by: "host", local: false,
    max_allowed_inflight: 2, max_allowed_batch_chunks: 64, max_allowed_batch_tokens: 50000 };
  const api = { embeddingRuntime: vi.fn(), changeEmbeddingRuntime: vi.fn() };
  let context: ReturnType<typeof contextFixture>;
  beforeEach(async () => {
    vi.clearAllMocks();
    context = contextFixture(["workspace.view"]);
    api.embeddingRuntime.mockReturnValue(of(runtime));
    api.changeEmbeddingRuntime.mockReturnValue(of(runtime));
    await TestBed.configureTestingModule({ imports: [EmbeddingSpeedComponent], providers: [
      provideNoopAnimations(), { provide: WorkspaceApiService, useValue: api },
      { provide: WorkspaceContextStore, useValue: context },
    ] }).compileComponents();
  });
  it("shows effective caps and prevents normal users from saving", () => {
    const view = TestBed.createComponent(EmbeddingSpeedComponent); view.detectChanges();
    expect(view.nativeElement.textContent).toContain("2 request đồng thời");
    expect(view.nativeElement.querySelector('form')).toBeNull();
    view.componentInstance["save"]();
    expect(api.changeEmbeddingRuntime).not.toHaveBeenCalled();
    view.destroy();
  });
  it("saves a preference without changing the embedding model", () => {
    context.accessInfo.update(info => ({ ...info, permissions: ["workspace.view", "ai.change_embedding"] }));
    const view = TestBed.createComponent(EmbeddingSpeedComponent); view.detectChanges();
    view.componentInstance["preference"] = { profile: "fast", max_inflight_requests: 4,
                                           retry_max_attempts: 12 };
    view.componentInstance["save"]();
    expect(api.changeEmbeddingRuntime).toHaveBeenCalledWith("workspace-1", { profile: "fast" });
    expect(view.componentInstance["runtime"]()?.effective_max_inflight).toBe(2);
    view.detectChanges();
    expect(view.nativeElement.textContent).toContain("Đã lưu tốc độ embedding");
    view.destroy();
  });
  it("cancels a pending response when navigating to a different workspace", () => {
    const pending = new Subject<typeof runtime>(); api.embeddingRuntime.mockReturnValueOnce(pending);
    const view = TestBed.createComponent(EmbeddingSpeedComponent); view.detectChanges();
    context.workspace.update(ws => ({ ...ws!, id: "workspace-2" })); view.detectChanges();
    pending.next({ ...runtime, effective_max_inflight: 4 });
    expect(view.componentInstance["runtime"]()?.effective_max_inflight).toBe(2);
    view.destroy();
  });
});
