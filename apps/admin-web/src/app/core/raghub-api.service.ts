import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';

import { session } from './api-auth.interceptor';

export interface Organization { id: string; name: string; slug: string; role: string; }
export interface Membership { user_id: string; email: string; role: 'OWNER' | 'ADMIN' | 'EDITOR' | 'VIEWER'; }
export interface Workspace { id: string; name: string; slug: string; organization_id: string; }
export interface DocumentItem { id: string; name: string; status: string; created_at: string;
  document_version_id: string | null; job_id: string | null; stage: string | null;
  progress: number | null; attempts: number | null; error_code: string | null;
  error_message: string | null; retryable: boolean; }
export type ProviderCapability = 'EMBEDDING' | 'CHAT';
export type ProviderType = 'OPENAI_COMPATIBLE' | 'GOOGLE_GEMINI' | 'LOCAL_TOKEN_HASH' | 'LOCAL_SENTENCE_TRANSFORMER' | 'OLLAMA';
export interface ProviderConfig {
  id: string; organization_id: string; name: string; provider_type: ProviderType;
  capability: ProviderCapability; base_url: string | null; model: string;
  dimension: number | null; config_json: Record<string, unknown>; enabled: boolean;
  has_secret: boolean; created_at: string; updated_at: string | null;
}
export interface ProviderConfigInput {
  name: string; provider_type: ProviderType; capability: ProviderCapability;
  model: string; base_url?: string | null; dimension?: number | null;
  secret?: string; config_json?: Record<string, unknown>; enabled?: boolean;
}
export interface ProviderConfigPatch extends Partial<ProviderConfigInput> { clear_secret?: boolean; }
export interface WorkspaceProviderBinding {
  workspace_id: string; embedding_provider_id: string | null; chat_provider_id: string | null;
  active_embedding_index_version_id: string | null; reindex_job_id: string | null;
}
export interface Chatbot {
  id: string; workspace_id: string; name: string; system_prompt: string;
  model: string | null; retrieval_limit: number; published: boolean;
  created_at: string; updated_at: string | null;
}
export interface ChatbotInput {
  name: string; system_prompt: string; model?: string | null;
  retrieval_limit: number; published: boolean;
}
export interface ChatRequest { message: string; conversation_id?: string | null; external_user_id?: string | null; }
export type ChatStreamEventName = 'conversation' | 'citations' | 'token' | 'usage' | 'done' | 'error';
export interface ChatStreamEvent { event: ChatStreamEventName; data: Record<string, unknown>; }
export interface AuthToken { access_token: string; token_type?: string; }
export interface CurrentUser { id: string; email: string; email_verified: boolean; }

export class SseEventParser {
  private buffer = '';

  push(chunk: string): ChatStreamEvent[] {
    this.buffer += chunk;
    const frames = this.buffer.split(/\r?\n\r?\n/);
    this.buffer = frames.pop() ?? '';
    return frames.flatMap((frame) => this.parse(frame));
  }

  flush(): ChatStreamEvent[] {
    const remaining = this.buffer;
    this.buffer = '';
    return this.parse(remaining);
  }

  private parse(frame: string): ChatStreamEvent[] {
    if (!frame.trim()) return [];
    const event = frame.match(/^event:\s*(.+)$/m)?.[1]?.trim();
    const data = frame.match(/^data:\s*(.+)$/m)?.[1];
    if (!event || !data) return [];
    try {
      return [{ event: event as ChatStreamEventName, data: JSON.parse(data) as Record<string, unknown> }];
    } catch {
      return [];
    }
  }
}

@Injectable({ providedIn: 'root' })
export class RaghubApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1';

  login(email: string, password: string) {
    return this.http.post<AuthToken>(`${this.base}/auth/login`, { email, password });
  }
  me() { return this.http.get<CurrentUser>(`${this.base}/auth/me`); }
  forgotPassword(email: string) {
    return this.http.post<{ message: string }>(`${this.base}/auth/password/forgot`, { email });
  }
  resetPassword(token: string, newPassword: string) {
    return this.http.post<void>(`${this.base}/auth/password/reset`, { token, new_password: newPassword });
  }
  changePassword(currentPassword: string, newPassword: string) {
    return this.http.post<AuthToken>(`${this.base}/auth/password/change`, {
      current_password: currentPassword,
      new_password: newPassword,
    });
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
  providers(organizationId: string) {
    return this.http.get<ProviderConfig[]>(`${this.base}/organizations/${organizationId}/providers`);
  }
  createProvider(organizationId: string, payload: ProviderConfigInput) {
    return this.http.post<ProviderConfig>(`${this.base}/organizations/${organizationId}/providers`, payload);
  }
  updateProvider(providerId: string, payload: ProviderConfigPatch) {
    return this.http.patch<ProviderConfig>(`${this.base}/providers/${providerId}`, payload);
  }
  testProvider(providerId: string) {
    return this.http.post(`${this.base}/providers/${providerId}/test`, {});
  }
  bindWorkspaceProviders(workspaceId: string, embeddingProviderId: string | null, chatProviderId: string | null) {
    return this.http.patch<WorkspaceProviderBinding>(`${this.base}/workspaces/${workspaceId}/providers`, {
      embedding_provider_id: embeddingProviderId,
      chat_provider_id: chatProviderId,
    });
  }
  chatbots(workspaceId: string) {
    return this.http.get<Chatbot[]>(`${this.base}/workspaces/${workspaceId}/chatbots`);
  }
  createChatbot(workspaceId: string, payload: ChatbotInput) {
    return this.http.post<Chatbot>(`${this.base}/workspaces/${workspaceId}/chatbots`, payload);
  }
  updateChatbot(chatbotId: string, payload: Partial<ChatbotInput>) {
    return this.http.patch<Chatbot>(`${this.base}/chatbots/${chatbotId}`, payload);
  }
  deleteChatbot(chatbotId: string) {
    return this.http.delete(`${this.base}/chatbots/${chatbotId}`);
  }

  async streamChat(chatbotId: string, payload: ChatRequest, onEvent: (event: ChatStreamEvent) => void): Promise<void> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'text/event-stream' };
    if (session.accessToken) headers['Authorization'] = `Bearer ${session.accessToken}`;
    if (session.organizationId) headers['X-Organization-ID'] = session.organizationId;

    try {
      const response = await fetch(`${this.base}/chatbots/${chatbotId}/chat`, {
        method: 'POST', headers, body: JSON.stringify(payload), credentials: 'include',
      });
      if (!response.ok || !response.body) {
        onEvent({ event: 'error', data: { message: `Không thể kết nối chatbot (HTTP ${response.status}).` } });
        return;
      }
      const parser = new SseEventParser();
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { value, done } = await reader.read();
        if (value) parser.push(decoder.decode(value, { stream: !done })).forEach(onEvent);
        if (done) break;
      }
      parser.flush().forEach(onEvent);
    } catch {
      onEvent({ event: 'error', data: { message: 'Kết nối chat bị gián đoạn. Hãy thử lại.' } });
    }
  }
}
