import { inject } from "@angular/core";
import { CanActivateFn, Router } from "@angular/router";
import { catchError, map, of } from "rxjs";

import { session } from "./api-auth.interceptor";
import { RaghubApiService } from "./raghub-api.service";
import { consoleOrganization } from "./console-organization";

export const adminOnly: CanActivateFn = () => {
  const api = inject(RaghubApiService);
  const router = inject(Router);
  if (!session.accessToken) {
    return router.createUrlTree(["/auth"]);
  }
  return api.organizations().pipe(
    map((organizations) => {
      const current = consoleOrganization(organizations);
      session.organizationId = current?.id ?? null;
      if (current && current.role === "ADMIN") {
        return true;
      }
      return router.createUrlTree(["/app/workspaces"]);
    }),
    catchError(() => of(router.createUrlTree(["/app/workspaces"]))),
  );
};
