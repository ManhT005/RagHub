import { TestBed } from "@angular/core/testing";
import { provideRouter, UrlTree } from "@angular/router";
import { firstValueFrom, isObservable, of } from "rxjs";

import { adminOnly } from "./admin.guard";
import { session } from "./api-auth.interceptor";
import { RaghubApiService } from "./raghub-api.service";

describe("adminOnly", () => {
  afterEach(() => {
    session.accessToken = null;
    session.organizationId = null;
  });

  async function runGuard(role: "ADMIN" | "WORKSPACE_ADMIN" | null) {
    session.accessToken = "test-token";
    session.organizationId = "org-1";
    await TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            organizations: () =>
              of(
                role
                  ? [{ id: "org-1", name: "Demo", slug: "demo", role }]
                  : [],
              ),
          },
        },
      ],
    }).compileComponents();
    const result = TestBed.runInInjectionContext(() =>
      adminOnly({} as never, {} as never),
    );
    return isObservable(result) ? firstValueFrom(result) : result;
  }

  it("allows ADMIN members", async () => {
    await expect(runGuard("ADMIN")).resolves.toBe(true);
  });

  it("redirects WORKSPACE_ADMIN members to workspaces", async () => {
    const result = (await runGuard("WORKSPACE_ADMIN")) as UrlTree;
    expect(result).toBeInstanceOf(UrlTree);
    expect(result.toString()).toBe("/app/workspaces");
  });

  it("redirects anonymous users to login", async () => {
    session.accessToken = null;
    await TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: RaghubApiService, useValue: { organizations: () => of([]) } },
      ],
    }).compileComponents();
    const result = TestBed.runInInjectionContext(() =>
      adminOnly({} as never, {} as never),
    );
    expect(result).toBeInstanceOf(UrlTree);
    expect((result as UrlTree).toString()).toBe("/auth");
  });
});
