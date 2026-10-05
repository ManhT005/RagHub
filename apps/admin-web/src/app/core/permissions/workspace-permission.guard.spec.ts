import { Component } from "@angular/core";
import { TestBed } from "@angular/core/testing";
import {
  ActivatedRouteSnapshot,
  convertToParamMap,
  provideRouter,
  Router,
  RouterStateSnapshot,
  UrlTree,
} from "@angular/router";
import { firstValueFrom, Observable, throwError } from "rxjs";
import { WorkspaceContextStore } from "../workspace-context/workspace-context.store";
import { contextFixture } from "../../features/selfhost-test-fixtures";
import {
  workspaceContextGuard,
  workspacePermissionGuard,
} from "./workspace-permission.guard";
import { legacyWorkspaceRedirect } from "../workspace-context/legacy-workspace.guard";
import { CanDirective } from "./can.directive";
@Component({
  imports: [CanDirective],
  template: `<button *appCan="'document.upload'">Upload</button>`,
})
class PermissionHost {}
describe("Workspace permission gates", () => {
  let context: ReturnType<typeof contextFixture>;
  beforeEach(() => {
    context = contextFixture(["workspace.view", "document.view"]);
    TestBed.configureTestingModule({
      imports: [PermissionHost],
      providers: [
        provideRouter([]),
        { provide: WorkspaceContextStore, useValue: context },
      ],
    });
  });
  it("reactively removes actions when a permission is revoked", () => {
    const view = TestBed.createComponent(PermissionHost);
    view.detectChanges();
    expect(view.nativeElement.querySelector("button")).toBeNull();
    context.accessInfo.set({
      ...context.accessInfo(),
      permissions: ["workspace.view", "document.view", "document.upload"],
    });
    view.detectChanges();
    expect(view.nativeElement.querySelector("button")).not.toBeNull();
    context.accessInfo.set({
      ...context.accessInfo(),
      permissions: ["workspace.view"],
    });
    view.detectChanges();
    expect(view.nativeElement.querySelector("button")).toBeNull();
    view.destroy();
  });
  it("redirects denied child routes without mounting their screen", () => {
    const result = TestBed.runInInjectionContext(() =>
      workspacePermissionGuard(
        {
          data: { permission: "ai.view" },
        } as unknown as ActivatedRouteSnapshot,
        {} as RouterStateSnapshot,
      ),
    );
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe(
      "/app/workspaces/workspace-1/overview?denied=1",
    );
  });
  it("handles direct URLs to inaccessible workspaces", async () => {
    context.load.mockReturnValue(throwError(() => ({ status: 403 })));
    const result = TestBed.runInInjectionContext(() =>
      workspaceContextGuard(
        {
          paramMap: convertToParamMap({ workspaceId: "hidden" }),
        } as ActivatedRouteSnapshot,
        {} as RouterStateSnapshot,
      ),
    );
    expect(
      TestBed.inject(Router).serializeUrl(
        await firstValueFrom(result as Observable<UrlTree>),
      ),
    ).toBe("/app/workspaces?denied=1");
  });
  it("maps old console bookmarks into the canonical workspace routes", () => {
    const result = TestBed.runInInjectionContext(() =>
      legacyWorkspaceRedirect(
        {
          paramMap: convertToParamMap({ workspaceId: "old" }),
          queryParamMap: convertToParamMap({ section: "settings" }),
          data: {},
        } as ActivatedRouteSnapshot,
        {} as RouterStateSnapshot,
      ),
    );
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe(
      "/app/workspaces/old/ai",
    );
  });
});
