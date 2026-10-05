import { inject } from "@angular/core";
import { CanActivateFn, Router } from "@angular/router";

/** Preserve bookmarks without mounting the old permission-unaware console. */
export const legacyWorkspaceRedirect: CanActivateFn = (route) => {
  const router = inject(Router);
  const id =
    route.paramMap.get("workspaceId") ??
    route.queryParamMap.get("workspaceId") ??
    route.queryParamMap.get("workspace");
  const oldSection =
    route.data["section"] ?? route.queryParamMap.get("section") ?? "overview";
  const section =
    (
      { settings: "ai", "ai-settings": "ai", chatbots: "chat" } as Record<
        string,
        string
      >
    )[oldSection] ?? oldSection;
  return id
    ? router.createUrlTree([
        "/app/workspaces",
        id,
        ["overview", "documents", "chat", "members", "ai"].includes(section)
          ? section
          : "overview",
      ])
    : router.createUrlTree(["/app/workspaces"]);
};
