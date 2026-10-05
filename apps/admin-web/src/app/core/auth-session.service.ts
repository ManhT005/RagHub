import { HttpBackend, HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, defer, finalize, firstValueFrom, from, map, of, shareReplay, switchMap, tap, throwError, timeout } from 'rxjs';
import { session } from './session-state';
@Injectable({ providedIn: 'root' })
export class AuthSessionService {
  // Bypass interceptors to avoid recursive refresh and circular injection.
  private readonly http = new HttpClient(inject(HttpBackend));
  private refreshInFlight$: Observable<string> | null = null;
  private knownUnauthenticated = false;
  private generation = 0;
  readonly restoreError = signal(false);
  accessToken(): string | null { return session.accessToken; }
  acceptToken(token: string): void {
    this.generation++;
    session.accessToken = token;
    this.knownUnauthenticated = false;
    this.restoreError.set(false);
  }
  login(email: string, password: string): Observable<void> {
    return this.http.post<{ access_token: string }>('/api/v1/auth/login', { email, password }, { withCredentials: true }).pipe(
      tap(result => this.acceptToken(result.access_token)), map(() => undefined),
    );
  }
  refresh(): Observable<string> {
    if (!this.refreshInFlight$) {
      const generation = this.generation;
      this.refreshInFlight$ = defer(() => {
        const send = () => this.http.post<{ access_token: string }>('/api/v1/auth/refresh', {}, { withCredentials: true }).pipe(timeout(15000));
        // Browser tabs share the cookie. Serialize rotation across tabs when Web Locks is available.
        return navigator.locks ? from((async () => await navigator.locks.request('raghub.refresh', () => firstValueFrom(send())))()) : send();
      }).pipe(
        map(result => {
          if (generation !== this.generation) throw new Error('Session changed during refresh');
          session.accessToken = result.access_token;
          this.knownUnauthenticated = false;
          this.restoreError.set(false);
          return result.access_token;
        }),
        catchError(error => {
          if (generation === this.generation && error instanceof HttpErrorResponse && error.status === 401) this.clearLocalSession();
          return throwError(() => error);
        }),
        finalize(() => { this.refreshInFlight$ = null; }),
        shareReplay({ bufferSize: 1, refCount: false }),
      );
    }
    return this.refreshInFlight$;
  }
  restoreSession(): Observable<boolean> {
    if (this.accessToken()) return of(true);
    if (this.knownUnauthenticated) return of(false);
    return this.refresh().pipe(
      map(() => true),
      catchError(error => {
        if (error instanceof HttpErrorResponse && error.status === 401) return of(false);
        this.restoreError.set(true);
        return throwError(() => error);
      }),
    );
  }
  logout(): Observable<void> {
    const pending = this.refreshInFlight$;
    this.clearLocalSession();
    // Wait for cookie rotation before revoking, so logout cannot leave a new session behind.
    return (pending ? pending.pipe(catchError(() => of(null))) : of(null)).pipe(
      switchMap(() => this.http.post<void>('/api/v1/auth/logout', {}, { withCredentials: true }).pipe(timeout(5000))),
      catchError(() => of(undefined)),
    );
  }
  clearLocalSession(): void {
    this.generation++;
    session.accessToken = null;
    session.organizationId = null;
    this.knownUnauthenticated = true;
  }
}
