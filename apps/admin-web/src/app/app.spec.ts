import { Location } from '@angular/common';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { AppComponent } from './app.component';
import { appConfig } from './app.config';

describe('AppComponent', () => {
  it('redirects legacy documents without a workspace to the workspace selector', async () => {
    sessionStorage.setItem('raghub.access-token', 'test-token');
    await TestBed.configureTestingModule({ providers: appConfig.providers }).compileComponents();
    const router = TestBed.inject(Router);
    const location = TestBed.inject(Location);
    await router.navigateByUrl('/documents');
    expect(location.path()).toBe('/app/workspaces');
  });

  it('redirects an unauthenticated profile visit to login', async () => {
    sessionStorage.removeItem('raghub.access-token');
    await TestBed.configureTestingModule({ providers: appConfig.providers }).compileComponents();
    const router = TestBed.inject(Router);
    const location = TestBed.inject(Location);
    await router.navigateByUrl('/app/profile');
    expect(location.path()).toContain('/auth');
  });

  it('hosts routed page content', async () => {
    await TestBed.configureTestingModule({ imports: [AppComponent], providers: appConfig.providers }).compileComponents();
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('router-outlet')).not.toBeNull();
  });
});
