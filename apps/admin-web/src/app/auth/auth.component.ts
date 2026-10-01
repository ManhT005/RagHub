import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { RaghubApiService } from '../core/raghub-api.service';
import { session } from '../core/api-auth.interceptor';

type AuthMode = 'login' | 'forgot';

@Component({
  selector: 'raghub-auth',
  imports: [FormsModule],
  templateUrl: './auth.component.html',
  styleUrl: './auth.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AuthComponent {
  protected email = '';
  protected password = '';
  protected mode: AuthMode = 'login';
  protected readonly error = signal('');
  protected readonly message = signal('');
  protected readonly loading = signal(false);
  private readonly api = inject(RaghubApiService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected setMode(mode: AuthMode): void {
    this.mode = mode;
    this.error.set('');
    this.message.set('');
  }

  protected submitCredentials(): void {
    this.error.set('');
    this.message.set('');
    this.loading.set(true);
    this.api.login(this.email, this.password).subscribe({
      next: ({ access_token }) => this.completeLogin(access_token),
      error: () => {
        this.error.set('Không thể đăng nhập. Hãy kiểm tra email và mật khẩu.');
        this.loading.set(false);
      },
    });
  }

  protected requestPasswordReset(): void {
    this.error.set('');
    this.loading.set(true);
    this.api.forgotPassword(this.email).subscribe({
      next: () => {
        this.message.set('Nếu email tồn tại, liên kết đặt lại mật khẩu đã được gửi.');
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Không thể gửi yêu cầu lúc này. Vui lòng thử lại.');
        this.loading.set(false);
      },
    });
  }

  private completeLogin(accessToken: string): void {
    session.accessToken = accessToken;
    this.loading.set(false);
    const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');
    void this.router.navigateByUrl(returnUrl?.startsWith('/') ? returnUrl : '/workspaces');
  }

}
