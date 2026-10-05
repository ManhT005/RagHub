import {
  ChangeDetectionStrategy,
  Component,
  inject,
  signal,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
import { RaghubApiService } from "../core/raghub-api.service";
import { AuthSessionService } from "../core/auth-session.service";

@Component({
  selector: "raghub-security",
  imports: [FormsModule],
  template: `<section class="security-card">
    <p class="eyebrow">TÀI KHOẢN</p>
    <h1>Đổi mật khẩu</h1>
    <form (ngSubmit)="submit()">
      <label
        >Mật khẩu hiện tại
        <input
          [(ngModel)]="currentPassword"
          name="current"
          type="password"
          autocomplete="current-password"
          required /></label
      ><label
        >Mật khẩu mới
        <input
          [(ngModel)]="newPassword"
          name="next"
          type="password"
          autocomplete="new-password"
          minlength="8"
          required /></label
      ><label
        >Nhập lại mật khẩu
        <input
          [(ngModel)]="confirmation"
          name="confirmation"
          type="password"
          autocomplete="new-password"
          minlength="8"
          required
      /></label>
      @if (error()) {
        <p class="error">{{ error() }}</p>
      }
      @if (success()) {
        <p class="success">{{ success() }}</p>
      }
      <button type="submit">Đổi mật khẩu</button>
    </form>
  </section>`,
  styles: [
    `
      .security-card {
        max-width: 560px;
        padding: 24px;
        border: 1px solid #e4edf8;
        border-radius: 12px;
        background: #fff;
      }
      .security-card form,
      label {
        display: grid;
        gap: 10px;
      }
      .security-card form {
        margin-top: 20px;
      }
      .security-card input {
        padding: 10px;
        border: 1px solid #dce8f6;
        border-radius: 8px;
      }
      .security-card button {
        padding: 11px;
        border: 0;
        border-radius: 8px;
        background: #1677ff;
        color: #fff;
        font-weight: 700;
      }
      .error {
        color: #d9363e;
      }
      .success {
        color: #1f9d68;
      }
    `,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SecurityComponent {
  protected currentPassword = "";
  protected newPassword = "";
  protected confirmation = "";
  protected readonly error = signal("");
  protected readonly success = signal("");
  private readonly api = inject(RaghubApiService);
  private readonly auth = inject(AuthSessionService);
  protected submit(): void {
    this.error.set("");
    this.success.set("");
    if (this.newPassword !== this.confirmation) {
      this.error.set("Hai mật khẩu mới không khớp.");
      return;
    }
    this.api.changePassword(this.currentPassword, this.newPassword).subscribe({
      next: ({ access_token }) => {
        this.auth.acceptToken(access_token);
        this.success.set(
          "Đổi mật khẩu thành công. Các phiên cũ đã bị thu hồi.",
        );
      },
      error: () =>
        this.error.set(
          "Mật khẩu hiện tại không đúng hoặc mật khẩu mới không hợp lệ.",
        ),
    });
  }
}
