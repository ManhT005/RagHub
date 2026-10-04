import { TestBed } from "@angular/core/testing";
import { provideNoopAnimations } from "@angular/platform-browser/animations";
import { of, Subject } from "rxjs";
import {
  DocumentApiService,
  DocumentMetadata,
} from "../../core/api/document-api.service";
import { ProviderApiService } from "../../core/api/provider-api.service";
import { WorkspaceApiService } from "../../core/api/workspace-api.service";
import { RaghubApiService } from "../../core/raghub-api.service";
import { WorkspaceContextStore } from "../../core/workspace-context/workspace-context.store";
import { contextFixture } from "../selfhost-test-fixtures";
import { WorkspaceDocumentsComponent } from "./workspace-documents.component";

describe("Workspace documents", () => {
  const doc = {
    id: "doc-1",
    name: "knowledge.md",
    status: "READY",
    document_version_id: "version-1",
    chunk_count: 3,
    progress: 100,
    created_at: "2026-10-04T00:00:00Z",
    size_bytes: 100,
    retryable: false,
  } as DocumentMetadata;
  const api = { list: vi.fn(), detail: vi.fn(), download: vi.fn() };
  const actions = {
    upload: vi.fn(),
    reindexDocument: vi.fn(),
    retryDocument: vi.fn(),
    deleteDocument: vi.fn(),
  };
  let context: ReturnType<typeof contextFixture>;
  beforeEach(async () => {
    vi.clearAllMocks();
    context = contextFixture(["workspace.view", "document.view"]);
    api.list.mockReturnValue(of([doc]));
    await TestBed.configureTestingModule({
      imports: [WorkspaceDocumentsComponent],
      providers: [
        provideNoopAnimations(),
        { provide: DocumentApiService, useValue: api },
        { provide: RaghubApiService, useValue: actions },
        { provide: ProviderApiService, useValue: {} },
        { provide: WorkspaceApiService, useValue: {} },
        { provide: WorkspaceContextStore, useValue: context },
      ],
    }).compileComponents();
  });
  afterEach(() => vi.useRealTimers());
  it("loads documents for a document-only user without requesting provider administration", () => {
    const view = TestBed.createComponent(WorkspaceDocumentsComponent);
    view.detectChanges();
    expect(api.list).toHaveBeenCalledWith("workspace-1");
    expect(api.list).toHaveBeenCalledTimes(1);
    expect(view.nativeElement.textContent).toContain("current-model");
    expect(view.nativeElement.textContent).not.toContain("+ Tải tài liệu lên");
    view.componentInstance["remove"](doc);
    view.componentInstance["reindex"](doc);
    expect(actions.deleteDocument).not.toHaveBeenCalled();
    expect(actions.reindexDocument).not.toHaveBeenCalled();
    view.destroy();
  });
  it("polls while processing and stops at READY or component destruction", () => {
    vi.useFakeTimers();
    api.list
      .mockReturnValueOnce(of([{ ...doc, status: "EMBEDDING" }]))
      .mockReturnValue(of([doc]));
    const view = TestBed.createComponent(WorkspaceDocumentsComponent);
    view.detectChanges();
    vi.advanceTimersByTime(3000);
    expect(api.list).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(9000);
    expect(api.list).toHaveBeenCalledTimes(2);
    expect(context.refresh).toHaveBeenCalledTimes(1);
    api.list.mockReturnValue(of([{ ...doc, status: "INDEXING" }]));
    view.componentInstance["load"]();
    view.destroy();
    vi.advanceTimersByTime(9000);
    expect(api.list).toHaveBeenCalledTimes(3);
  });
  it("rejects oversized and unsupported files before submitting an upload", () => {
    const view = TestBed.createComponent(WorkspaceDocumentsComponent),
      component = view.componentInstance;
    component["chooseFiles"]({
      target: {
        files: [{ name: "big.pdf", size: 26 * 1024 * 1024 }],
        value: "",
      },
    } as unknown as Event);
    expect(component["files"]()).toHaveLength(0);
    expect(component["error"]()).toContain("25 MB");
    component["chooseFiles"]({
      target: { files: [new File(["content"], "bad.docx")], value: "" },
    } as unknown as Event);
    expect(component["files"]()).toHaveLength(0);
    expect(component["error"]()).toContain("PDF");
    expect(actions.upload).not.toHaveBeenCalled();
    view.destroy();
  });
  it("maps every real ingestion stage and keeps unknown metadata empty", () => {
    const view = TestBed.createComponent(WorkspaceDocumentsComponent),
      component = view.componentInstance;
    expect(component["statuses"].map((item) => item[0])).toEqual([
      "UPLOADED",
      "QUEUED",
      "PARSING",
      "CHUNKING",
      "EMBEDDING",
      "INDEXING",
      "READY",
      "FAILED",
    ]);
    expect(component["size"](null)).toBe("—");
    view.destroy();
  });
  it("cancels the previous workspace response when a reused route changes scope", () => {
    const stale = new Subject<DocumentMetadata[]>();
    api.list.mockReturnValueOnce(stale).mockReturnValue(of([]));
    const view = TestBed.createComponent(WorkspaceDocumentsComponent);
    view.detectChanges();
    context.workspace.set({ ...context.workspace()!, id: "workspace-2" });
    view.detectChanges();
    stale.next([doc]);
    expect(view.componentInstance["documents"]()).toHaveLength(0);
    expect(api.list).toHaveBeenLastCalledWith("workspace-2");
    view.destroy();
  });
});
