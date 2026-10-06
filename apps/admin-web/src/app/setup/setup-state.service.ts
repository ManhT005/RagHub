import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, defer, finalize, map, of, shareReplay, tap, throwError, timeout } from 'rxjs';

export interface SetupStatus { status: 'UNINITIALIZED' | 'INITIALIZING' | 'INITIALIZED'; initialized: boolean; }
export interface SetupInput {
  owner_email: string;
  owner_password: string;
  organization_name: string;
  organization_slug: string;
  ai_mode: 'SKIP' | 'LOCAL';
}
export interface SetupResult {
  access_token: string;
  user_id: string;
  organization_id: string;
  provider_ids: string[];
}
export interface Readiness { name: string; ready: boolean; }

@Injectable({ providedIn: 'root' })
export class SetupStateService {
  private readonly http = inject(HttpClient);
  private cached: SetupStatus | null = null;
  private inFlight$: Observable<SetupStatus> | null = null;
  readonly unavailable = signal(false);

  status(): Observable<SetupStatus> {
    if (this.cached) return of(this.cached);
    if (!this.inFlight$) {
      this.inFlight$ = defer(() => this.http.get<SetupStatus>('/api/v1/setup/status')).pipe(
        timeout(15000),
        tap(status => { this.cached = status; this.unavailable.set(false); }),
        catchError(error => { this.unavailable.set(true); return throwError(() => error); }),
        finalize(() => this.inFlight$ = null),
        shareReplay({ bufferSize: 1, refCount: false }),
      );
    }
    return this.inFlight$;
  }
  markInitialized(): void { this.cached = { status: 'INITIALIZED', initialized: true }; }
  invalidate(): void { this.cached = null; }
  initialize(payload: SetupInput): Observable<SetupResult> {
    return this.http.post<SetupResult>('/api/v1/setup/initialize', payload, { withCredentials: true }).pipe(
      timeout(30000), tap(() => this.markInitialized()),
    );
  }
  readiness(): Observable<Readiness[]> {
    const dependencies = ['postgres', 'redis', 'elasticsearch', 'minio'];
    return this.http.get('/health/ready').pipe(
      timeout(15000),
      map(() => [{ name: 'API', ready: true }, ...dependencies.map(name => ({ name, ready: true }))]),
      catchError((error: HttpErrorResponse) => {
        const failed = error.error?.error?.details?.dependencies;
        return of([{ name: 'API', ready: error.status === 503 }, ...dependencies.map(name => ({ name, ready: !!failed && !(name in failed) }))]);
      }),
    );
  }
}
