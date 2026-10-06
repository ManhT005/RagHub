import {
  ChangeDetectionStrategy,
  Component,
  inject,
  signal,
  ViewChild,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
import { ActivatedRoute, RouterLink } from "@angular/router";
import { RaghubApiService } from "../core/raghub-api.service";
import { PasswordToggleDirective } from "../shared/password-toggle.directive";
import { TurnstileComponent } from "./turnstile.component";

@Component({
  selector: "raghub-reset-password",
  imports: [FormsModule, PasswordToggleDirective, RouterLink, TurnstileComponent],
  template: `<main class="auth-card">
    <p class="eyebrow">BẢO MẬT RAGHUB</p>
    <h1>Đặt lại mật khẩu</h1>
    <p>Tạo mật khẩu mới có ít nhất 8 ký tự.</p>
    <form (ngSubmit)="submit()">
      <label
        >Mật khẩu mới
        <input
          [(ngModel)]="password"
          name="password"
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
      <raghub-turnstile action="reset_password" (tokenChange)="turnstileToken = $event" (availabilityChange)="turnstileRequired.set($event)" />
      <button type="submit" [disabled]="turnstileRequired() && !turnstileToken">Đặt lại mật khẩu</button>
    </form>
    <a routerLink="/auth">Quay lại đăng nhập</a>
  </main>`,
  styleUrl: "./auth.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ResetPasswordComponent {
  protected password = "";
  protected confirmation = "";
  protected readonly error = signal("");
  protected readonly success = signal("");
  protected readonly turnstileRequired = signal(true);
  protected turnstileToken = "";
  @ViewChild(TurnstileComponent) private turnstile?: TurnstileComponent;
  private readonly token =
    inject(ActivatedRoute).snapshot.queryParamMap.get("token") ?? "";
  private readonly api = inject(RaghubApiService);
  protected submit(): void {
    this.error.set("");
    if (!this.token) {
      this.error.set("Liên kết đặt lại mật khẩu không hợp lệ.");
      return;
    }
    if (this.password !== this.confirmation) {
      this.error.set("Hai mật khẩu không khớp.");
      return;
    }
    this.api
      .resetPassword(this.token, this.password, this.turnstileToken)
      .subscribe({
        next: () =>
          this.success.set("Đã đổi mật khẩu. Bạn có thể đăng nhập lại."),
        error: () => {
          this.error.set("Liên kết không hợp lệ, đã hết hạn hoặc đã được sử dụng.");
          this.turnstile?.reset();
        },
      });
  }
}
