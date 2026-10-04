import {
  ChangeDetectionStrategy,
  Component,
  inject,
  signal,
} from "@angular/core";
import { HttpClient } from "@angular/common/http";
import { RouterLink } from "@angular/router";
import { RaghubApiService } from "../core/raghub-api.service";
import { consoleOrganization } from "../core/console-organization";

@Component({
  selector: "raghub-system",
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<main>
    <h1>Hệ thống</h1>
    <p>Trạng thái cài đặt RagHub của bạn.</p>
    <section>
      <h2>Health</h2>
      <p role="status">{{ status() }}</p>
      <button type="button" (click)="check()" [disabled]="busy()">
        Kiểm tra lại
      </button>
      <p>
        Kiểm tra database, hàng đợi, tìm kiếm và lưu trữ. Kiểm tra model ở Cấu
        hình AI.
      </p>
    </section>
    @if (isOwner()) {
      <section>
        <h2>Người dùng</h2>
        <p>Quản lý quyền truy cập workspace.</p>
        <a routerLink="/system/users">Mở quản lý người dùng</a>
      </section>
    }
    <section>
      <h2>Bảo mật</h2>
      <a routerLink="/app/security">Mật khẩu và phiên đăng nhập</a>
    </section>
  </main>`,
  styles: `
    section {
      padding: 24px;
      color: var(--rh-text);
      background: var(--rh-surface);
      border: 1px solid var(--rh-border);
      border-radius: 12px;
      margin: 20px 0;
    }
    button,
    a {
      min-height: 44px;
      display: inline-flex;
      align-items: center;
    }
    button {
      padding: 10px 16px;
      color: var(--rh-text);
      background: var(--rh-surface-raised);
      border: 1px solid var(--rh-border);
      border-radius: 6px;
      cursor: pointer;
    }
    :is(a, button):focus-visible {
      outline: 3px solid var(--rh-indigo);
      outline-offset: 2px;
    }
  `,
})
export class SystemComponent {
  protected readonly status = signal("Đang kiểm tra…");
  protected readonly busy = signal(false);
  protected readonly isOwner = signal(false);
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
    this.http.get("/health/ready").subscribe({
      next: () => {
        this.status.set("Các dịch vụ nền tảng sẵn sàng.");
        this.busy.set(false);
      },
      error: () => {
        this.status.set("Có dịch vụ chưa sẵn sàng. Kiểm tra log của cài đặt.");
        this.busy.set(false);
      },
    });
  }
}
