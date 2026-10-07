import { HttpClient } from "@angular/common/http";
import { ChangeDetectionStrategy, Component, inject, signal } from "@angular/core";
import { RouterLink } from "@angular/router";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzCardModule } from "ng-zorro-antd/card";

import { consoleOrganization } from "../core/console-organization";
import { RaghubApiService } from "../core/raghub-api.service";

@Component({
  selector: "raghub-system",
  imports: [RouterLink, NzAlertModule, NzButtonModule, NzCardModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<main class="selfhost-page system-page">
    <header class="page-heading">
      <h1>Hệ thống</h1>
    </header>

    <nz-card nzTitle="Health" [nzBordered]="true">
      <p class="card-description">Theo dõi khả năng sẵn sàng của các dịch vụ nền tảng.</p>
      <nz-alert
        [nzType]="ready() === true ? 'success' : ready() === false ? 'warning' : 'info'"
        [nzMessage]="status()"
        nzShowIcon
      />
      <div class="card-actions">
        <button nz-button nzType="primary" [nzLoading]="busy()" (click)="check()">Kiểm tra lại</button>
      </div>
      <p class="hint">Kiểm tra database, hàng đợi, tìm kiếm và lưu trữ. Kiểm tra model ở Cấu hình AI.</p>
    </nz-card>

    @if (isOwner()) {
      <nz-card nzTitle="Người dùng" [nzBordered]="true">
        <p class="card-description">Quản lý quyền truy cập workspace.</p>
        <div class="card-actions">
          <a nz-button nzType="primary" routerLink="/system/users">Mở quản lý người dùng</a>
        </div>
      </nz-card>
    }

    <nz-card nzTitle="Bảo mật" [nzBordered]="true">
      <p class="card-description">Cập nhật mật khẩu và quản lý các phiên đăng nhập.</p>
      <div class="card-actions">
        <a nz-button nzType="primary" routerLink="/app/security">Mật khẩu và phiên đăng nhập</a>
      </div>
    </nz-card>
  </main>`,
  styles: [`
    .system-page { max-width: 920px; display: grid; gap: 16px; }
    .system-page .page-heading { margin-bottom: 4px; }
    .card-description, .hint { color: var(--rh-muted); }
    .card-description { margin: 0 0 16px; }
    .card-actions { display: flex; gap: 8px; margin-top: 16px; }
    .hint { margin: 12px 0 0; font-size: 13px; }
  `],
})
export class SystemComponent {
  protected readonly status = signal("Đang kiểm tra…");
  protected readonly busy = signal(false);
  protected readonly isOwner = signal(false);
  protected readonly ready = signal<boolean | null>(null);
  private readonly http = inject(HttpClient);

  constructor() {
    inject(RaghubApiService)
      .organizations()
      .subscribe((items) => {
        this.isOwner.set(consoleOrganization(items)?.role === "ADMIN");
      });
    this.check();
  }

  protected check(): void {
    this.busy.set(true);
    this.ready.set(null);
    this.http.get("/health/ready").subscribe({
      next: () => {
        this.status.set("Các dịch vụ nền tảng sẵn sàng.");
        this.ready.set(true);
        this.busy.set(false);
      },
      error: () => {
        this.status.set("Có dịch vụ chưa sẵn sàng. Kiểm tra log của cài đặt.");
        this.ready.set(false);
        this.busy.set(false);
      },
    });
  }
}
