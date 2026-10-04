import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { NzButtonModule } from 'ng-zorro-antd/button';
import { NzInputModule } from 'ng-zorro-antd/input';
import { NzTagModule } from 'ng-zorro-antd/tag';
import { NzAlertModule } from 'ng-zorro-antd/alert';
import { NzPopconfirmModule } from 'ng-zorro-antd/popconfirm';
import { forkJoin, finalize } from 'rxjs';
import { ProviderApiService, ProviderCatalogItem, ProviderConnection } from '../../core/api/provider-api.service';
import { RaghubApiService } from '../../core/raghub-api.service';
import { session } from '../../core/api-auth.interceptor';
import { apiError } from '../../core/api/api-error';
import { ProviderOnboardingComponent } from './provider-onboarding.component';
import { ProviderLogoComponent } from '../../shared/provider-logo/provider-logo.component';

@Component({
  selector: 'raghub-ai-providers',
  imports: [FormsModule, RouterLink, NzButtonModule, NzInputModule, NzTagModule, NzAlertModule, NzPopconfirmModule, ProviderOnboardingComponent, ProviderLogoComponent],
  templateUrl: './ai-providers.component.html', changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiProvidersComponent {
  protected readonly connections = signal<ProviderConnection[]>([]);
  protected readonly catalog = signal<ProviderCatalogItem[]>([]);
  protected readonly loading = signal(false);
  protected readonly busy = signal('');
  protected readonly error = signal('');
  protected readonly notice = signal('');
  protected readonly drawerOpen = signal(false);
  protected readonly editing = signal<ProviderConnection | null>(null);
  protected readonly query = signal('');
  protected readonly status = signal('');
  protected readonly filtered = computed(() => this.connections().filter(item => item.name.toLowerCase().includes(this.query().toLowerCase()) && (!this.status() || item.status === this.status())));
  protected organizationId = '';
  private readonly api = inject(ProviderApiService);
  private readonly auth = inject(RaghubApiService);
  private readonly destroyRef = inject(DestroyRef);
  constructor() {
    this.auth.organizations().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: items => {
        this.organizationId = items.find(item => item.id === session.organizationId)?.id ?? items[0]?.id ?? '';
        session.organizationId = this.organizationId || null; this.load();
      }, error: error => this.error.set(apiError(error))
    });
  }
  protected load() {
    if (!this.organizationId) return;
    this.loading.set(true);
    forkJoin({ connections: this.api.connections(this.organizationId), catalog: this.api.catalog() })
      .pipe(finalize(() => this.loading.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
        next: data => { this.connections.set(data.connections); this.catalog.set(data.catalog); }, error: error => this.error.set(apiError(error)),
      });
  }
  protected open(connection: ProviderConnection | null = null) { this.editing.set(connection); this.drawerOpen.set(true); }
  protected test(connection: ProviderConnection) {
    if (this.busy()) return;
    this.busy.set(connection.id); this.error.set('');
    this.api.test(connection.id).pipe(finalize(() => { this.busy.set(''); this.load(); }), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { this.notice.set(result.error_code ? apiError({ error: { error: { code: result.error_code } } }) : `Kết nối thành công · ${result.latency_ms} ms`); }, error: error => this.error.set(apiError(error)),
    });
  }
  protected toggle(connection: ProviderConnection) {
    if (this.busy()) return;
    this.busy.set(connection.id);
    this.api.update(connection.id, { enabled: !connection.enabled }).pipe(finalize(() => { this.busy.set(''); this.load(); }), takeUntilDestroyed(this.destroyRef)).subscribe({ error: error => this.error.set(apiError(error)) });
  }
  protected remove(connection: ProviderConnection) {
    if (this.busy()) return;
    this.busy.set(connection.id);
    this.api.remove(connection.id).pipe(finalize(() => { this.busy.set(''); this.load(); }), takeUntilDestroyed(this.destroyRef)).subscribe({ error: error => this.error.set(apiError(error)) });
  }
  protected capabilities(connection: ProviderConnection) { return this.catalog().find(item => item.provider_type === connection.provider_type)?.capabilities ?? []; }
}
