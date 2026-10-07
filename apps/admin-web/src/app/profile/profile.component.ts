import { ChangeDetectionStrategy, Component, inject, signal } from "@angular/core";
import { Router, RouterLink } from "@angular/router";
import { NzAvatarModule } from "ng-zorro-antd/avatar";
import { NzBadgeModule } from "ng-zorro-antd/badge";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzCardModule } from "ng-zorro-antd/card";
import { NzSpinModule } from "ng-zorro-antd/spin";

import { CurrentUser, RaghubApiService } from "../core/raghub-api.service";
import { session } from "../core/api-auth.interceptor";

@Component({
  selector: "raghub-profile",
  imports: [RouterLink, NzAvatarModule, NzBadgeModule, NzButtonModule, NzCardModule, NzSpinModule],
  template: `<main class="selfhost-page profile-page">
    <header class="page-heading">
      <h1>Tài khoản</h1>
    </header>
    @if (user(); as currentUser) {
      <nz-card class="profile-card" [nzBordered]="true">
        <div class="identity-row">
          <nz-avatar [nzSize]="56" [nzText]="currentUser.email.slice(0, 1).toUpperCase()" />
          <div class="identity">
            <span>Email đăng nhập</span>
            <strong>{{ currentUser.email }}</strong>
            <nz-badge [nzStatus]="currentUser.email_verified ? 'success' : 'warning'"
              [nzText]="currentUser.email_verified ? 'Email đã xác thực' : 'Email chưa xác thực'" />
          </div>
        </div>
      </nz-card>
      <nz-card class="security-card" [nzBordered]="true">
        <div>
          <h2>Mật khẩu và phiên đăng nhập</h2>
          <p>Đổi mật khẩu để bảo vệ tài khoản và thu hồi các phiên cũ.</p>
        </div>
        <a nz-button nzType="primary" routerLink="/app/security">Đổi mật khẩu</a>
      </nz-card>
    } @else {
      <div class="loading-state"><nz-spin nzSimple /><span>Đang tải thông tin tài khoản…</span></div>
    }
  </main>`,
  styles: [`
    .profile-page { max-width: 820px; display: grid; gap: 16px; }
    .profile-page .page-heading { margin-bottom: 4px; }
    .identity-row { display: flex; align-items: center; gap: 18px; }
    .identity { display: grid; gap: 5px; }
    .identity > span { color: var(--rh-muted); font-size: 13px; }
    .identity strong { color: var(--rh-text); font-size: 16px; }
    .identity ::ng-deep .ant-badge-status-text { color: var(--rh-muted); }
    .security-card ::ng-deep .ant-card-body { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
    .security-card h2 { margin: 0; color: var(--rh-text); font-size: 16px; }
    .security-card p { margin: 6px 0 0; color: var(--rh-muted); font-size: 13px; }
    .loading-state { display: flex; align-items: center; gap: 12px; min-height: 88px; color: var(--rh-muted); }
    @media (max-width: 560px) {
      .security-card ::ng-deep .ant-card-body { align-items: flex-start; flex-direction: column; }
    }
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
        void this.router.navigate(["/auth"], { queryParams: { returnUrl: "/app/profile" } });
      },
    });
  }
}
