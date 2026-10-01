import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { CurrentUser, RaghubApiService } from '../core/raghub-api.service';
import { session } from '../core/api-auth.interceptor';

@Component({
  selector: 'raghub-profile',
  imports: [RouterLink],
  template: `
    <section class="profile-page">
      <div class="profile-heading"><p>Tài khoản</p><h1>Thông tin cá nhân</h1><span>Quản lý danh tính và bảo mật đăng nhập.</span></div>
      @if (user(); as currentUser) {
        <article class="profile-card">
          <div class="avatar">{{ currentUser.email.slice(0, 1).toUpperCase() }}</div>
          <div class="identity"><span>Email đăng nhập</span><strong>{{ currentUser.email }}</strong><small [class.verified]="currentUser.email_verified">{{ currentUser.email_verified ? 'Email đã xác thực' : 'Email chưa xác thực' }}</small></div>
        </article>
        <article class="security-card"><div><strong>Mật khẩu và phiên đăng nhập</strong><p>Đổi mật khẩu để bảo vệ tài khoản và thu hồi các phiên cũ.</p></div><a routerLink="/app/security">Đổi mật khẩu</a></article>
      } @else { <p class="loading">Đang tải thông tin tài khoản…</p> }
    </section>
  `,
  styles: [`
    .profile-page{max-width:820px;display:grid;gap:18px}.profile-heading p{margin:0 0 8px;color:#1677ff;font-size:13px;font-weight:800}.profile-heading h1{margin:0;color:#092b60;font-size:30px;letter-spacing:-.03em}.profile-heading span,.profile-card span,.profile-card small,.security-card p{color:#6683ad}.profile-heading span{display:block;margin-top:7px}.profile-card,.security-card{display:flex;gap:18px;align-items:center;padding:24px;border:1px solid #dce8f6;border-radius:16px;background:#fff;box-shadow:0 12px 30px rgba(35,91,163,.06)}.avatar{display:grid;width:54px;height:54px;place-items:center;border-radius:50%;background:#e8f2ff;color:#1677ff;font-size:20px;font-weight:800}.identity{display:grid;gap:5px}.identity strong{color:#092b60;font-size:17px}.identity small{font-weight:700}.identity small.verified{color:#15966b}.security-card{justify-content:space-between}.security-card strong{color:#092b60}.security-card p{margin:5px 0 0;font-size:13px}.security-card a{padding:10px 14px;border-radius:8px;color:#fff;background:#1677ff;font-weight:700;text-decoration:none;white-space:nowrap}.loading{color:#6683ad}@media(max-width:560px){.security-card{align-items:flex-start;flex-direction:column}}
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProfileComponent {
  protected readonly user = signal<CurrentUser | null>(null);
  private readonly api = inject(RaghubApiService);
  private readonly router = inject(Router);

  constructor() {
    this.api.me().subscribe({
      next: (user) => this.user.set(user),
      error: () => {
        session.accessToken = null;
        void this.router.navigate(['/auth'], { queryParams: { returnUrl: '/app/profile' } });
      },
    });
  }
}
