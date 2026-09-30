import { Routes } from '@angular/router';
import { AuthComponent } from './auth/auth.component';
import { ChatbotsComponent } from './chatbots/chatbots.component';
import { DashboardComponent } from './dashboard/dashboard.component';
import { DocumentsComponent } from './documents/documents.component';
import { WorkspaceConsoleComponent } from './workspace-console/workspace-console.component';
import { WorkspacesComponent } from './workspaces/workspaces.component';
import { AdminLayoutComponent } from './layouts/admin-layout.component';
import { LandingComponent } from './landing/landing.component';
import { PublicPageComponent } from './landing/public-page.component';
import { ChatbotSettingsComponent } from './chatbots/chatbot-settings.component';

export const routes: Routes = [
  { path: '', pathMatch: 'full', component: LandingComponent, title: 'RagHub' },
  { path: 'tinh-nang', component: PublicPageComponent, data: { page: 'features' }, title: 'Tính năng | RAGHub' },
  { path: 'giai-phap', component: PublicPageComponent, data: { page: 'solutions' }, title: 'Giải pháp | RAGHub' },
  { path: 'lien-he', component: PublicPageComponent, data: { page: 'contact' }, title: 'Liên hệ | RAGHub' },
  { path: 'auth', component: AuthComponent, title: 'Tài khoản | RagHub' },
  { path: 'app', component: AdminLayoutComponent, children: [
    { path: 'overview', component: DashboardComponent }, { path: 'workspaces', component: WorkspacesComponent },
    { path: 'workspace-console', component: WorkspaceConsoleComponent }, { path: 'documents', component: DocumentsComponent },
    { path: 'chatbots/:id/settings', component: ChatbotSettingsComponent }, { path: 'chatbots', component: ChatbotsComponent }, { path: '', pathMatch: 'full', redirectTo: 'overview' },
  ]},
  { path: 'workspaces', pathMatch: 'full', redirectTo: 'app/workspaces' }, { path: 'documents', pathMatch: 'full', redirectTo: 'app/documents' },
  { path: 'chatbots', pathMatch: 'full', redirectTo: 'app/chatbots' }, { path: 'settings', pathMatch: 'full', redirectTo: 'app/workspaces' }, { path: '**', redirectTo: '' },
];
