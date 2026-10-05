import { inject } from "@angular/core";
import { CanActivateFn, CanActivateChildFn, Router } from "@angular/router";
import { catchError, map, of } from "rxjs";
import { WorkspaceContextStore } from "../workspace-context/workspace-context.store";
import { WorkspacePermission } from "./permission.types";

export const workspaceContextGuard: CanActivateFn = (route) => {
  const context = inject(WorkspaceContextStore),
    router = inject(Router);
  return context.load(route.paramMap.get("workspaceId")!).pipe(
    map(() => true),
    catchError(() =>
      of(
        router.createUrlTree(["/app/workspaces"], {
          queryParams: { denied: "1" },
        }),
      ),
    ),
  );
};
export const workspacePermissionGuard: CanActivateChildFn = (route) => {
  const context = inject(WorkspaceContextStore),
    router = inject(Router);
  const permission = route.data["permission"] as
    | WorkspacePermission
    | undefined;
  return (
    !permission ||
    context.can(permission) ||
    router.createUrlTree(
      ["/app/workspaces", context.workspace()!.id, "overview"],
      { queryParams: { denied: "1" } },
    )
  );
};
