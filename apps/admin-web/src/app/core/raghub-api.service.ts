import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';

export interface Organization { id: string; name: string; slug: string; role: string; }
export interface Membership { user_id: string; email: string; role: 'OWNER' | 'ADMIN' | 'EDITOR' | 'VIEWER'; }
export interface Workspace { id: string; name: string; slug: string; organization_id: string; }
export interface DocumentItem { id: string; name: string; status: string; created_at: string;
  document_version_id: string | null; job_id: string | null; stage: string | null;
  progress: number | null; attempts: number | null; error_code: string | null;
  error_message: string | null; retryable: boolean; }

@Injectable({ providedIn: 'root' })
export class RaghubApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1';

  login(email: string, password: string) {
    return this.http.post<{ access_token: string }>(`${this.base}/auth/login`, { email, password });
  }
  register(email: string, password: string) {
    return this.http.post<{ access_token: string }>(`${this.base}/auth/register`, { email, password });
  }
  organizations() { return this.http.get<Organization[]>(`${this.base}/organizations`); }
  createOrganization(name: string, slug: string) {
    return this.http.post<Organization>(`${this.base}/organizations`, { name, slug });
  }
  members(organizationId: string) {
    return this.http.get<Membership[]>(`${this.base}/organizations/${organizationId}/members`);
  }
  saveMember(organizationId: string, email: string, role: Membership['role']) {
    return this.http.put<Membership>(`${this.base}/organizations/${organizationId}/members`, { email, role });
  }
  deleteMember(organizationId: string, userId: string) {
    return this.http.delete(`${this.base}/organizations/${organizationId}/members/${userId}`);
  }
  workspaces() { return this.http.get<Workspace[]>(`${this.base}/workspaces`); }
  createWorkspace(name: string, slug: string) {
    return this.http.post<Workspace>(`${this.base}/workspaces`, { name, slug });
  }
  documents(workspaceId: string) {
    return this.http.get<DocumentItem[]>(`${this.base}/workspaces/${workspaceId}/documents`);
  }
  upload(workspaceId: string, file: File) {
    const body = new FormData();
    body.append('file', file);
    return this.http.post(`${this.base}/workspaces/${workspaceId}/documents`, body);
  }
  retryDocument(workspaceId: string, versionId: string) {
    return this.http.post(`${this.base}/workspaces/${workspaceId}/document-versions/${versionId}/retry`, {});
  }
  reindexDocument(workspaceId: string, versionId: string) {
    return this.http.post(`${this.base}/workspaces/${workspaceId}/document-versions/${versionId}/reindex`, {});
  }
  deleteDocument(workspaceId: string, documentId: string) {
    return this.http.delete(`${this.base}/workspaces/${workspaceId}/documents/${documentId}`);
  }
}
