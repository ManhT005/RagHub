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
