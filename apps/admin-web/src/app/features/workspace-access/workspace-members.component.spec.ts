import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { AccessApiService } from '../../core/api/access-api.service';
import { WorkspaceContextStore } from '../../core/workspace-context/workspace-context.store';
import { contextFixture } from '../selfhost-test-fixtures';
import { WorkspaceMembersComponent } from './workspace-members.component';
describe('Workspace member permissions', () => {
  const api = { members: vi.fn(() => of([])), candidates: vi.fn(() => of([])), assign: vi.fn(() => of({})), update: vi.fn() };
  beforeEach(async () => { vi.clearAllMocks(); await TestBed.configureTestingModule({ imports: [WorkspaceMembersComponent], providers: [provideNoopAnimations(), { provide: AccessApiService, useValue: api }, { provide: WorkspaceContextStore, useValue: contextFixture(['workspace.view', 'member.view', 'member.manage']) }] }).compileComponents(); });
  it('adds view dependencies and removes dependent mutations together', () => {
    const view = TestBed.createComponent(WorkspaceMembersComponent), component = view.componentInstance;
    component['toggle']('document.delete', true); expect(component['grants']).toEqual(expect.arrayContaining(['workspace.view', 'document.view', 'document.delete']));
    component['toggle']('document.view', false); expect(component['grants']).toEqual(['workspace.view']);
    component['toggle']('ai.change_embedding', true); expect(component['grants']).toContain('ai.view'); view.destroy();
  });
  it('assigns explicit workspace permissions without changing the organization role', () => {
    const view = TestBed.createComponent(WorkspaceMembersComponent), component = view.componentInstance; view.detectChanges();
    component['selectedUserId'] = 'member-1'; component['toggle']('document.upload', true); component['save']();
    expect(api.assign).toHaveBeenCalledWith('workspace-1', 'member-1', expect.arrayContaining(['document.upload', 'document.view', 'workspace.view']));
    expect(component['grants'].some(permission => permission.startsWith('system.'))).toBe(false); view.destroy();
  });
});
