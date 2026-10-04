import { TestBed } from "@angular/core/testing";
import { provideNoopAnimations } from "@angular/platform-browser/animations";
import { of } from "rxjs";
import { ProviderApiService } from "../../core/api/provider-api.service";
import { WorkspaceApiService } from "../../core/api/workspace-api.service";
import { WorkspaceContextStore } from "../../core/workspace-context/workspace-context.store";
import { contextFixture, workspaceFixture } from "../selfhost-test-fixtures";
import { EmbeddingProfileComponent } from "./embedding-profile.component";
describe("Safe embedding selection", () => {
  const api = {
    preview: vi.fn(),
    changeEmbedding: vi.fn(),
    reindexJob: vi.fn(),
    retryReindex: vi.fn(),
  };
  const providers = { workspaceModels: vi.fn() };
  let context: ReturnType<typeof contextFixture>;
  beforeEach(async () => {
    vi.clearAllMocks();
    context = contextFixture([
      "workspace.view",
      "ai.view",
      "ai.change_embedding",
    ]);
    api.preview.mockReturnValue(
      of({
        current_model: {
          id: "model-1",
          model: "current-model",
          dimension: 384,
        },
        target_model: { id: "model-2", model: "new-model", dimension: 768 },
        requires_reindex: true,
        documents_affected: 1,
        chunks_affected: 3,
      }),
    );
    api.changeEmbedding.mockReturnValue(of({ reindex_job_id: "job-1" }));
    providers.workspaceModels.mockReturnValue(
      of([
        {
          id: "model-2",
          model: "new-model",
          dimension: 768,
          enabled: true,
          connection_enabled: true,
          connection_status: "CONNECTED",
          availability_status: "AVAILABLE",
        },
        {
          id: "bad",
          enabled: true,
          connection_enabled: true,
          connection_status: "ERROR",
          availability_status: "AVAILABLE",
        },
      ]),
    );
    await TestBed.configureTestingModule({
      imports: [EmbeddingProfileComponent],
      providers: [
        provideNoopAnimations(),
        { provide: WorkspaceContextStore, useValue: context },
        { provide: WorkspaceApiService, useValue: api },
        { provide: ProviderApiService, useValue: providers },
      ],
    }).compileComponents();
  });
  afterEach(() => vi.useRealTimers());
  it("requires impact preview and explicit confirmation before changing the model", () => {
    const view = TestBed.createComponent(EmbeddingProfileComponent),
      component = view.componentInstance;
    view.detectChanges();
    component["choose"]();
    expect(component["models"]()).toHaveLength(1);
    component["selected"] = "model-2";
    component["apply"]();
    expect(api.changeEmbedding).not.toHaveBeenCalled();
    component["review"]();
    component["apply"]();
    expect(api.changeEmbedding).not.toHaveBeenCalled();
    component["confirmed"] = true;
    component["apply"]();
    expect(api.changeEmbedding).toHaveBeenCalledWith("workspace-1", "model-2");
    expect(context.refresh).toHaveBeenCalled();
    view.destroy();
  });
  it("invalidates confirmation when the target selection changes", () => {
    const view = TestBed.createComponent(EmbeddingProfileComponent),
      component = view.componentInstance;
    component["selected"] = "model-2";
    component["review"]();
    component["confirmed"] = true;
    component["selected"] = "model-3";
    component["selectionChanged"]();
    component["apply"]();
    expect(api.changeEmbedding).not.toHaveBeenCalled();
    expect(component["preview"]()).toBeNull();
    view.destroy();
  });
  it("keeps the current embedding profile and stops polling after reindex failure", () => {
    vi.useFakeTimers();
    context.workspace.set({
      ...workspaceFixture,
      reindex_job_id: "job-1",
      reindex_status: "RUNNING",
    });
    api.reindexJob.mockReturnValue(
      of({
        id: "job-1",
        status: "FAILED",
        total_documents: 1,
        processed_documents: 0,
        failed_documents: 1,
      }),
    );
    const view = TestBed.createComponent(EmbeddingProfileComponent),
      component = view.componentInstance;
    view.detectChanges();
    vi.advanceTimersByTime(0);
    view.detectChanges();
    expect(component["retryable"]()).toBe(true);
    expect(context.workspace()?.embedding_model?.model).toBe("current-model");
    vi.advanceTimersByTime(9000);
    expect(api.reindexJob).toHaveBeenCalledTimes(1);
    view.destroy();
  });
});
