import { Routes } from "@angular/router";
import { authenticated, authenticatedChild } from "./core/auth.guard";
import { adminOnly } from "./core/admin.guard";
import {
  workspaceContextGuard,
  workspacePermissionGuard,
} from "./core/permissions/workspace-permission.guard";
import { legacyWorkspaceRedirect } from "./core/workspace-context/legacy-workspace.guard";
import { chatbotSettingsGuard } from "./core/permissions/chatbot-settings.guard";

export const routes: Routes = [
  {
    path: "",
    pathMatch: "full",
    loadComponent: () =>
      import("./landing/landing.component").then((m) => m.LandingComponent),
    title: "RagHub",
  },
  ...["tinh-nang", "giai-phap", "lien-he"].map((path, index) => ({
    path,
    loadComponent: () =>
      import("./landing/public-page.component").then(
        (m) => m.PublicPageComponent,
      ),
    data: { page: ["features", "solutions", "contact"][index] },
  })),
  {
    path: "auth/reset-password",
    loadComponent: () =>
      import("./auth/reset-password.component").then(
        (m) => m.ResetPasswordComponent,
      ),
  },
  {
    path: "auth",
    loadComponent: () =>
      import("./auth/auth.component").then((m) => m.AuthComponent),
  },
  {
    path: "app",
    loadComponent: () =>
      import("./layouts/console-layout.component").then(
        (m) => m.ConsoleLayoutComponent,
      ),
    canActivate: [authenticated],
    canActivateChild: [authenticatedChild],
    children: [
      {
        path: "overview",
        loadComponent: () =>
          import("./dashboard/dashboard.component").then(
            (m) => m.DashboardComponent,
          ),
      },
      {
        path: "workspaces",
        loadComponent: () =>
          import("./features/workspaces/workspaces-page.component").then(
            (m) => m.WorkspacesPageComponent,
          ),
      },
      {
        path: "workspaces/:workspaceId",
        loadComponent: () =>
          import("./features/workspace-shell/workspace-shell.component").then(
            (m) => m.WorkspaceShellComponent,
          ),
        canActivate: [workspaceContextGuard],
        canActivateChild: [workspacePermissionGuard],
        children: [
          {
            path: "overview",
            loadComponent: () =>
              import(
                "./features/workspace-shell/workspace-overview.component"
              ).then((m) => m.WorkspaceOverviewComponent),
          },
          {
            path: "documents",
            loadComponent: () =>
              import(
                "./features/workspace-documents/workspace-documents.component"
              ).then((m) => m.WorkspaceDocumentsComponent),
            data: { permission: "document.view" },
          },
          {
            path: "members",
            loadComponent: () =>
              import(
                "./features/workspace-access/workspace-members.component"
              ).then((m) => m.WorkspaceMembersComponent),
            data: { permission: "member.view" },
          },
          {
            path: "ai",
            loadComponent: () =>
              import("./features/workspace-ai/workspace-ai.component").then(
                (m) => m.WorkspaceAiComponent,
              ),
            data: { permission: "ai.view" },
          },
          {
            path: "chat",
            loadComponent: () =>
              import("./features/workspace-chat/workspace-chat.component").then(
                (m) => m.WorkspaceChatComponent,
              ),
            data: { permission: "chat.use" },
          },
          { path: "", pathMatch: "full", redirectTo: "overview" },
        ],
      },
      { path: "users", pathMatch: "full", redirectTo: "/system/users" },
      {
        path: "ai-settings",
        pathMatch: "full",
        redirectTo: "/system/ai/providers",
      },
      {
        path: "workspace-console/:workspaceId",
        canActivate: [legacyWorkspaceRedirect],
        children: [],
      },
      {
        path: "workspace-console",
        canActivate: [legacyWorkspaceRedirect],
        children: [],
      },
      {
        path: "documents",
        canActivate: [legacyWorkspaceRedirect],
        data: { section: "documents" },
        children: [],
      },
      {
        path: "chatbots/:id/settings",
        loadComponent: () =>
          import("./chatbots/chatbot-settings.component").then(
            (m) => m.ChatbotSettingsComponent,
          ),
        canActivate: [chatbotSettingsGuard],
      },
      {
        path: "chatbots",
        canActivate: [legacyWorkspaceRedirect],
        data: { section: "chat" },
        children: [],
      },
      {
        path: "security",
        loadComponent: () =>
          import("./auth/security.component").then((m) => m.SecurityComponent),
      },
      {
        path: "profile",
        loadComponent: () =>
          import("./profile/profile.component").then((m) => m.ProfileComponent),
      },
      { path: "", pathMatch: "full", redirectTo: "overview" },
    ],
  },
  {
    path: "system",
    loadComponent: () =>
      import("./layouts/console-layout.component").then(
        (m) => m.ConsoleLayoutComponent,
      ),
    canActivate: [authenticated],
    canActivateChild: [authenticatedChild],
    children: [
      {
        path: "ai/providers",
        loadComponent: () =>
          import("./features/ai-providers/ai-providers.component").then(
            (m) => m.AiProvidersComponent,
          ),
        canActivate: [adminOnly],
      },
      {
        path: "ai/models",
        loadComponent: () =>
          import("./features/model-registry/model-registry.component").then(
            (m) => m.ModelRegistryComponent,
          ),
        canActivate: [adminOnly],
      },
      {
        path: "users",
        loadComponent: () =>
          import("./users/users.component").then((m) => m.UsersComponent),
        canActivate: [adminOnly],
      },
      {
        path: "",
        pathMatch: "full",
        loadComponent: () =>
          import("./system/system.component").then((m) => m.SystemComponent),
      },
    ],
  },
  { path: "workspaces", pathMatch: "full", redirectTo: "app/workspaces" },
  { path: "documents", pathMatch: "full", redirectTo: "app/documents" },
  { path: "chatbots", pathMatch: "full", redirectTo: "app/chatbots" },
  { path: "settings", pathMatch: "full", redirectTo: "app/workspaces" },
  { path: "**", redirectTo: "" },
];
