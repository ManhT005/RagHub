import { inject } from "@angular/core";
import { CanActivateFn, Router } from "@angular/router";
import { catchError, map, of, switchMap } from "rxjs";
import { RaghubApiService } from "../raghub-api.service";
import { AccessApiService } from "../api/access-api.service";
export const chatbotSettingsGuard: CanActivateFn = (route) => {
  const api = inject(RaghubApiService),
    access = inject(AccessApiService),
    router = inject(Router);
  return api.chatbot(route.paramMap.get("id")!).pipe(
    switchMap((bot) =>
      access
        .permissions(bot.workspace_id)
        .pipe(
          map(
            (info) =>
              info.permissions.includes("workspace.edit") ||
              router.createUrlTree(
                ["/app/workspaces", bot.workspace_id, "chat"],
                { queryParams: { denied: "1" } },
              ),
          ),
        ),
    ),
    catchError(() =>
      of(
        router.createUrlTree(["/app/workspaces"], {
          queryParams: { denied: "1" },
        }),
      ),
    ),
  );
};
