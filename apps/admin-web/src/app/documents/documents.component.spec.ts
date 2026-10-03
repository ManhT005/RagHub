import { TestBed } from "@angular/core/testing";
import { ActivatedRoute, convertToParamMap } from "@angular/router";
import { of } from "rxjs";
import { vi } from "vitest";

import { RaghubApiService } from "../core/raghub-api.service";
import { DocumentsComponent } from "./documents.component";

describe("DocumentsComponent ingestion errors", () => {
  for (const retryable of [false, true]) {
    it(`shows safe errors and retry availability ${retryable}`, async () => {
      await TestBed.configureTestingModule({
        imports: [DocumentsComponent],
        providers: [
          {
            provide: RaghubApiService,
            useValue: {
              workspaces: () => of([{ id: "workspace", name: "Workspace" }]),
              documents: () =>
                of([
                  {
                    id: "document",
                    name: "test.pdf",
                    status: "FAILED",
                    stage: "FAILED",
                    created_at: "2026-09-22T00:00:00Z",
                    document_version_id: "version",
                    error_code: retryable ? "INDEX_UNAVAILABLE" : "INVALID_PDF",
                    error_message: "password=secret host=private.internal",
                    retryable,
                  },
                ]),
            },
          },
        ],
      }).compileComponents();
      const fixture = TestBed.createComponent(DocumentsComponent);
      fixture.detectChanges();
      const element: HTMLElement = fixture.nativeElement;
      expect(element.textContent).not.toContain("private.internal");
      expect(element.textContent).not.toContain("password=secret");
      expect(element.textContent).toContain(
        retryable ? "tạm thời không khả dụng" : "PDF hợp lệ",
      );
      const buttons = Array.from(element.querySelectorAll("button"));
      expect(
        buttons.some((button) => button.textContent?.trim() === "Thử lại"),
      ).toBe(retryable);
      fixture.destroy();
    });
  }

  it("uses a flat toolbar and paginates documents at 10 rows per page", async () => {
    const documents = Array.from({ length: 11 }, (_, index) => ({
      id: `document-${index}`,
      name: `document-${index}.pdf`,
      status: "READY",
      stage: "READY",
      progress: 100,
      created_at: "2026-09-22T00:00:00Z",
      document_version_id: `version-${index}`,
    }));

    await TestBed.configureTestingModule({
      imports: [DocumentsComponent],
      providers: [
        {
          provide: RaghubApiService,
          useValue: {
            workspaces: () => of([{ id: "workspace", name: "Workspace" }]),
            documents: () => of(documents),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(DocumentsComponent);
    fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement;

    expect(element.querySelector(".documents-toolbar nz-select")).not.toBeNull();
    expect(element.querySelector(".documents-toolbar .upload-trigger")).not.toBeNull();
    expect(element.querySelector(".table-panel")).toBeNull();
    expect(element.querySelectorAll("tbody tr.ant-table-row").length).toBe(10);
    expect(element.querySelector(".ant-pagination")).not.toBeNull();
    fixture.destroy();
  });

  it("shows file selection only after opening the upload dialog", async () => {
    await TestBed.configureTestingModule({
      imports: [DocumentsComponent],
      providers: [
        {
          provide: RaghubApiService,
          useValue: {
            workspaces: () => of([{ id: "workspace", name: "Workspace" }]),
            documents: () => of([]),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(DocumentsComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('input[type="file"]')).toBeNull();

    (
      fixture.nativeElement.querySelector(".upload-trigger") as HTMLButtonElement
    ).click();
    fixture.detectChanges();

    expect(document.body.querySelector(".document-upload-modal nz-upload")).not.toBeNull();
    expect(document.body.querySelector('.document-upload-modal input[type="file"]')).not.toBeNull();
    fixture.destroy();
  });

  it("selects the workspace requested by the workspace list", async () => {
    const documents = vi.fn(() => of([]));
    await TestBed.configureTestingModule({
      imports: [DocumentsComponent],
      providers: [
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParamMap: convertToParamMap({ workspaceId: "workspace-2" }),
            },
          },
        },
        {
          provide: RaghubApiService,
          useValue: {
            workspaces: () =>
              of([
                { id: "workspace-1", name: "Một" },
                { id: "workspace-2", name: "Hai" },
              ]),
            documents,
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(DocumentsComponent);
    fixture.detectChanges();

    expect(documents).toHaveBeenCalledWith("workspace-2");
    expect((fixture.componentInstance as any).workspaceId).toBe("workspace-2");
    fixture.destroy();
  });
});
