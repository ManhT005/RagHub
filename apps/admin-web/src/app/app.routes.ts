import { Routes } from '@angular/router';

import { DashboardComponent } from './dashboard/dashboard.component';
import { AuthComponent } from './auth/auth.component';
import { DocumentsComponent } from './documents/documents.component';
import { WorkspacesComponent } from './workspaces/workspaces.component';

export const routes: Routes = [
  { path: '', pathMatch: 'full', component: DashboardComponent, title: 'Overview | RagHub' },
  { path: 'auth', component: AuthComponent, title: 'Sign in | RagHub' },
  { path: 'workspaces', component: WorkspacesComponent, title: 'Workspaces | RagHub' },
  { path: 'documents', component: DocumentsComponent, title: 'Documents | RagHub' },
  { path: '**', redirectTo: '' },
];
