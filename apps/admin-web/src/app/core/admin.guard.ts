import { inject } from "@angular/core";
import { CanActivateFn, Router } from "@angular/router";
import { catchError, map, of } from "rxjs";

import { session } from "./api-auth.interceptor";
import { RaghubApiService } from "./raghub-api.service";

export const adminOnly: CanActivateFn = () => {
  const api = inject(RaghubApiService);
  const router = inject(Router);
  if (!session.accessToken) {
    return router.createUrlTree(["/auth"]);
  }
  return api.organizations().pipe(
    map((organizations) => {
      const current =
        organizations.find((item) => item.id === session.organizationId) ??
        organizations[0];
      if (current && current.role === "ADMIN") {
        return true;
      }
      return router.createUrlTree(["/app/workspaces"]);
    }),
    catchError(() => of(router.createUrlTree(["/app/workspaces"]))),
  );
};
