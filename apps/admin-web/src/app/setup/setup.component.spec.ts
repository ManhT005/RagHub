import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject, of } from 'rxjs';
import { AuthSessionService } from '../core/auth-session.service';
import { RaghubApiService } from '../core/raghub-api.service';
import { session } from '../core/session-state';
import { SetupComponent } from './setup.component';
import { SetupResult, SetupStateService } from './setup-state.service';

describe('SetupComponent', () => {
  let fixture: ComponentFixture<SetupComponent>;
  let response: Subject<SetupResult>;
  let setup: { initialize: ReturnType<typeof vi.fn>; readiness: ReturnType<typeof vi.fn>; markInitialized: ReturnType<typeof vi.fn> };
  let auth: { acceptToken: ReturnType<typeof vi.fn> };
  beforeEach(async () => {
    sessionStorage.clear(); response = new Subject<SetupResult>();
    setup = { initialize: vi.fn(() => response), readiness: vi.fn(() => of([{ name: 'API', ready: true }, { name: 'postgres', ready: true }])), markInitialized: vi.fn() };
    auth = { acceptToken: vi.fn() };
    await TestBed.configureTestingModule({ imports: [SetupComponent], providers: [provideRouter([]), { provide: SetupStateService, useValue: setup }, { provide: AuthSessionService, useValue: auth }, { provide: RaghubApiService, useValue: { testProvider: () => of({ status: 'OK' }) } }] }).compileComponents();
    fixture = TestBed.createComponent(SetupComponent); fixture.detectChanges();
  });
  const click = () => { fixture.nativeElement.querySelector('button[type=submit]').click(); fixture.detectChanges(); };
  const input = (id: string, value: string) => {
    const field = fixture.nativeElement.querySelector('#' + id) as HTMLInputElement;
    field.value = value; field.dispatchEvent(new Event('input')); fixture.detectChanges();
  };
  it('validates owner confirmation, submits once, and hands off the session', async () => {
    click(); await fixture.whenStable();
    input('owner-email', 'owner@example.com'); input('owner-password', 'strong-password'); input('owner-confirmation', 'wrong-password');
    await fixture.whenStable(); click();
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain('trùng nhau');
    input('owner-confirmation', 'strong-password'); await fixture.whenStable(); click();
    await fixture.whenStable(); click(); // organization
    await fixture.whenStable(); click(); // skip AI
    click(); click();
    expect(setup.initialize).toHaveBeenCalledTimes(1);
    expect(setup.initialize.mock.calls[0][0]).toMatchObject({ owner_email: 'owner@example.com', ai_mode: 'SKIP', organization_slug: 'raghub' });
    response.next({ access_token: 'token', user_id: 'owner', organization_id: 'org', provider_ids: [] }); response.complete();
    fixture.detectChanges();
    expect(auth.acceptToken).toHaveBeenCalledWith('token');
    expect(session.organizationId).toBe('org');
    expect(fixture.nativeElement.textContent).toContain('Khởi tạo thành công');
    expect(fixture.nativeElement.querySelector('a[href="/app/workspaces"]')).not.toBeNull();
  });
  it('blocks initialization while required services are unavailable', () => {
    setup.readiness.mockReturnValue(of([{ name: 'postgres', ready: false }]));
    fixture = TestBed.createComponent(SetupComponent); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button[type=submit]').disabled).toBe(true);
    expect(setup.initialize).not.toHaveBeenCalled();
  });
});
