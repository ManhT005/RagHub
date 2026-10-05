import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, RouterStateSnapshot, UrlTree, provideRouter } from '@angular/router';
import { Observable } from 'rxjs';
import { authenticated } from './auth.guard';

describe('authenticated guard', () => {
  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
  });
  for (const status of [200, 401, 503]) {
    it(`resolves cookie restoration ${status} before deciding route`, () => {
      let result: boolean | UrlTree | undefined;
      TestBed.runInInjectionContext(() => (authenticated({} as ActivatedRouteSnapshot, { url: '/app/workspaces' } as RouterStateSnapshot) as Observable<boolean | UrlTree>).subscribe(value => result = value));
      const http = TestBed.inject(HttpTestingController);
      const request = http.expectOne('/api/v1/auth/refresh');
      if (status === 200) request.flush({ access_token: 'restored' });
      else request.flush({}, { status, statusText: 'Error' });
      if (status === 200) expect(result).toBe(true);
      if (status === 401) expect(result).toBeInstanceOf(UrlTree);
      if (status === 503) expect(result).toBe(false);
      http.verify();
    });
  }
});
