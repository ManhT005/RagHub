import { Location } from '@angular/common';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { AppComponent } from './app.component';
import { appConfig } from './app.config';

describe('AppComponent', () => {
  it('redirects legacy documents to the app documents route', async () => {
    await TestBed.configureTestingModule({ providers: appConfig.providers }).compileComponents();
    const router = TestBed.inject(Router);
    const location = TestBed.inject(Location);
    await router.navigateByUrl('/documents');
    expect(location.path()).toBe('/app/documents');
  });

  it('hosts routed page content', async () => {
    await TestBed.configureTestingModule({ imports: [AppComponent], providers: appConfig.providers }).compileComponents();
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('router-outlet')).not.toBeNull();
  });
});
