import { Routes } from '@angular/router';

import { DashboardComponent } from './dashboard/dashboard.component';
import { AuthComponent } from './auth/auth.component';
import { DocumentsComponent } from './documents/documents.component';
import { WorkspacesComponent } from './workspaces/workspaces.component';

export const routes: Routes = [
  { path: '', pathMatch: 'full', component: DashboardComponent, title: 'Tổng quan | RagHub' },
  { path: 'auth', component: AuthComponent, title: 'Tài khoản | RagHub' },
  { path: 'workspaces', component: WorkspacesComponent, title: 'Không gian làm việc | RagHub' },
  { path: 'documents', component: DocumentsComponent, title: 'Tài liệu | RagHub' },
  { path: '**', redirectTo: '' },
];
