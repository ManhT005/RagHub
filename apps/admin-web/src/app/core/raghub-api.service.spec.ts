import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { RaghubApiService, SseEventParser } from './raghub-api.service';

describe('RaghubApiService chatbot endpoints', () => {
  let api: RaghubApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(RaghubApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('sends the selected workspace scope when saving a member', () => {
    api.saveMember('organization-1', 'lan@example.com', 'WORKSPACE_ADMIN', ['workspace-2']).subscribe();

    const request = http.expectOne('/api/v1/organizations/organization-1/members');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({
      email: 'lan@example.com',
      role: 'WORKSPACE_ADMIN',
      workspace_ids: ['workspace-2'],
    });
    request.flush({
      user_id: 'user-1',
      email: 'lan@example.com',
      role: 'WORKSPACE_ADMIN',
      workspace_ids: ['workspace-2'],
    });
  });
  it('loads providers for the selected organization', () => {
    api.providers('organization-1').subscribe();

    const request = http.expectOne('/api/v1/organizations/organization-1/providers');
    expect(request.request.method).toBe('GET');
    request.flush([]);
  });

  it('creates a chatbot in the selected workspace', () => {
    api.createChatbot('workspace-1', {
      name: 'Trợ lý tài liệu',
      system_prompt: 'Trả lời dựa trên tài liệu.',
      retrieval_limit: 5,
      published: false,
    }).subscribe();

    const request = http.expectOne('/api/v1/workspaces/workspace-1/chatbots');
    expect(request.request.method).toBe('POST');
    expect(request.request.body.name).toBe('Trợ lý tài liệu');
    request.flush({ id: 'chatbot-1' });
  });

  it('binds the chosen embedding and chat providers to a workspace', () => {
    api.bindWorkspaceProviders('workspace-1', 'embedding-1', 'chat-1').subscribe();

    const request = http.expectOne('/api/v1/workspaces/workspace-1/providers');
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ embedding_provider_id: 'embedding-1', chat_provider_id: 'chat-1' });
    request.flush({ workspace_id: 'workspace-1', embedding_provider_id: 'embedding-1', chat_provider_id: 'chat-1' });
  });

  it('requests admin users with server pagination of ten per page', () => {
    api.adminUsers('lan', 2).subscribe();

    const request = http.expectOne(
      (req) => req.url === '/api/v1/admin/users' && req.params.get('page_size') === '10',
    );
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('q')).toBe('lan');
    expect(request.request.params.get('page')).toBe('2');
    request.flush({ items: [], page: 2, page_size: 10, total: 0 });
  });

  it('creates admin users and updates their status', () => {
    api.createAdminUser('lan@example.com', 'mat-khau-123', 'Lan').subscribe();
    const create = http.expectOne('/api/v1/admin/users');
    expect(create.request.method).toBe('POST');
    expect(create.request.body).toEqual({
      email: 'lan@example.com',
      password: 'mat-khau-123',
      display_name: 'Lan',
    });
    create.flush({ id: 'user-1' });

    api.updateAdminUser('user-1', 'Lan Nguyen').subscribe();
    const rename = http.expectOne('/api/v1/admin/users/user-1');
    expect(rename.request.method).toBe('PATCH');
    expect(rename.request.body).toEqual({ display_name: 'Lan Nguyen' });
    rename.flush({ id: 'user-1', display_name: 'Lan Nguyen' });

    api.updateAdminUserStatus('user-1', 'DISABLED').subscribe();
    const status = http.expectOne('/api/v1/admin/users/user-1/status');
    expect(status.request.method).toBe('PATCH');
    expect(status.request.body).toEqual({ status: 'DISABLED' });
    status.flush({ id: 'user-1', status: 'DISABLED' });
  });
});

describe('SseEventParser', () => {
  it('keeps incomplete frames and returns parsed events in order', () => {
    const parser = new SseEventParser();

    expect(parser.push('event: token\ndata: {"delta":"Xin ')).toEqual([]);
    expect(parser.push('chào"}\n\nevent: done\ndata: {}\n\n')).toEqual([
      { event: 'token', data: { delta: 'Xin chào' } },
      { event: 'done', data: {} },
    ]);
  });
});

describe('RaghubApiService authentication endpoints', () => {
  let api: RaghubApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(RaghubApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('supports forgot, reset, and change password flows', () => {
    api.forgotPassword('user@example.com').subscribe();
    http.expectOne('/api/v1/auth/password/forgot').flush({ message: 'sent' });

    api.resetPassword('reset-token', 'new-password').subscribe();
    const reset = http.expectOne('/api/v1/auth/password/reset');
    expect(reset.request.body).toEqual({ token: 'reset-token', new_password: 'new-password' });
    reset.flush(null);

    api.changePassword('old-password', 'new-password').subscribe();
    const change = http.expectOne('/api/v1/auth/password/change');
    expect(change.request.body).toEqual({ current_password: 'old-password', new_password: 'new-password' });
    change.flush({ access_token: 'new-access' });
  });
});
