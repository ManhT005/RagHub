import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { catchError, finalize, forkJoin, map, of } from 'rxjs';
import { AuthSessionService } from '../core/auth-session.service';
import { RaghubApiService } from '../core/raghub-api.service';
import { session } from '../core/session-state';
import { Readiness, SetupStateService } from './setup-state.service';

@Component({
  selector: 'raghub-setup',
  imports: [FormsModule, RouterLink],
  templateUrl: './setup.component.html',
  styleUrl: './setup.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SetupComponent {
  protected readonly steps = ['Hệ thống', 'Owner', 'Tổ chức', 'AI', 'Xác nhận', 'Hoàn tất'];
  protected readonly step = signal(0);
  protected readonly busy = signal(false);
  protected readonly error = signal('');
  protected readonly readiness = signal<Readiness[]>([]);
  protected readonly providerChecks = signal<{ name: string; ready: boolean }[]>([]);
  protected readonly checkingProviders = signal(false);
  protected email = '';
  protected password = '';
  protected confirmation = '';
  protected organizationName = 'RagHub';
  protected organizationSlug = 'raghub';
  protected aiMode: 'SKIP' | 'LOCAL' | 'EXTERNAL' = 'SKIP';
  private providerIds: string[] = [];
  private readonly setup = inject(SetupStateService);
  private readonly auth = inject(AuthSessionService);
  private readonly api = inject(RaghubApiService);
  private readonly router = inject(Router);

  constructor() { this.checkReadiness(); }

  protected checkReadiness(): void {
    this.busy.set(true);
    this.setup.readiness().pipe(finalize(() => this.busy.set(false))).subscribe(checks => this.readiness.set(checks));
  }
  protected systemReady(): boolean {
    return this.readiness().length > 0 && this.readiness().every(check => check.ready);
  }
  protected next(): void {
    this.error.set('');
    if (this.busy() || this.step() >= 4) return;
    if (this.step() === 0 && !this.systemReady()) return;
    if (this.step() === 1 && (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.email.trim()) || this.password.length < 12 || this.password.length > 128 || this.password !== this.confirmation)) {
      this.error.set('Nhập email hợp lệ và mật khẩu từ 12–128 ký tự. Hai mật khẩu phải trùng nhau.'); return;
    }
    if (this.step() === 2 && (!this.organizationName.trim() || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(this.organizationSlug) || this.organizationSlug.length > 100)) {
      this.error.set('Nhập tên tổ chức và slug gồm chữ thường, số, dấu gạch ngang.'); return;
    }
    this.changeStep(this.step() + 1);
  }
  protected back(): void { if (!this.busy()) this.changeStep(Math.max(0, this.step() - 1)); }
  private changeStep(step: number): void {
    this.step.set(step); this.error.set('');
    setTimeout(() => document.getElementById('setup-step-title')?.focus());
  }
  protected finish(): void {
    if (this.busy() || this.step() !== 4) return;
    this.error.set(''); this.busy.set(true);
    this.setup.initialize({
      owner_email: this.email.trim(), owner_password: this.password,
      organization_name: this.organizationName.trim(), organization_slug: this.organizationSlug,
      ai_mode: this.aiMode === 'LOCAL' ? 'LOCAL' : 'SKIP',
    }).pipe(finalize(() => this.busy.set(false))).subscribe({
      next: result => {
        this.auth.acceptToken(result.access_token); session.organizationId = result.organization_id;
        this.providerIds = result.provider_ids;
        this.password = ''; this.confirmation = '';
        this.changeStep(5);
        if (this.providerIds.length) this.testProviders();
      },
      error: error => {
        if (error.status === 409 && error.error?.error?.code === 'INSTALLATION_ALREADY_INITIALIZED') {
          this.setup.markInitialized(); this.password = ''; this.confirmation = '';
          void this.router.navigateByUrl('/auth');
        } else {
          this.error.set('Không thể hoàn tất lúc này. Hãy thử lại. Nếu hệ thống đã khởi tạo, bạn có thể đăng nhập bằng tài khoản Owner vừa nhập.');
        }
      },
    });
  }
  protected testProviders(): void {
    if (this.checkingProviders() || !this.providerIds.length) return;
    this.checkingProviders.set(true);
    forkJoin(this.providerIds.map((id, index) => this.api.testProvider(id).pipe(
      map(result => ({ name: index === 0 ? 'Embedding' : 'Chat', ready: result.status === 'OK' })),
      catchError(() => of({ name: index === 0 ? 'Embedding' : 'Chat', ready: false })),
    ))).pipe(finalize(() => this.checkingProviders.set(false))).subscribe(checks => this.providerChecks.set(checks));
  }
}
