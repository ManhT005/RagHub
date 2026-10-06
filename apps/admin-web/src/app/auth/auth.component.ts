import { PasswordToggleDirective } from "../shared/password-toggle.directive";
import {
  ChangeDetectionStrategy,
  Component,
  inject,
  signal,
  ViewChild,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
import { ActivatedRoute, Router } from "@angular/router";

import { RaghubApiService } from "../core/raghub-api.service";
import { AuthSessionService } from "../core/auth-session.service";
import { TurnstileComponent } from "./turnstile.component";

type AuthMode = "login" | "forgot";

@Component({
  selector: "raghub-auth",
  imports: [FormsModule, PasswordToggleDirective, TurnstileComponent],
  templateUrl: "./auth.component.html",
  styleUrl: "./auth.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AuthComponent {
  protected email = "";
  protected password = "";
  protected mode: AuthMode = "login";
  protected readonly error = signal("");
  protected readonly message = signal("");
  protected readonly loading = signal(false);
  protected readonly turnstileRequired = signal(true);
  protected turnstileToken = "";
  @ViewChild(TurnstileComponent) private turnstile?: TurnstileComponent;
  private readonly api = inject(RaghubApiService);
  private readonly auth = inject(AuthSessionService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected setMode(mode: AuthMode): void {
    this.mode = mode;
    this.error.set("");
    this.message.set("");
    this.turnstileToken = "";
  }

  protected submitCredentials(): void {
    this.error.set("");
    this.message.set("");
    this.loading.set(true);
    this.auth.login(this.email, this.password, this.turnstileToken).subscribe({
      next: () => this.completeLogin(),
      error: () => {
        this.error.set("Không thể đăng nhập. Hãy kiểm tra email và mật khẩu.");
        this.loading.set(false);
        this.turnstile?.reset();
      },
    });
  }

  protected requestPasswordReset(): void {
    this.error.set("");
    this.loading.set(true);
    this.api.forgotPassword(this.email, this.turnstileToken).subscribe({
      next: () => {
        this.message.set(
          "Nếu email tồn tại, liên kết đặt lại mật khẩu đã được gửi.",
        );
        this.loading.set(false);
        this.turnstile?.reset();
      },
      error: () => {
        this.error.set("Không thể gửi yêu cầu lúc này. Vui lòng thử lại.");
        this.loading.set(false);
        this.turnstile?.reset();
      },
    });
  }

  private completeLogin(): void {
    this.loading.set(false);
    const returnUrl = this.route.snapshot.queryParamMap.get("returnUrl");
    void this.router.navigateByUrl(
      returnUrl?.startsWith("/") ? returnUrl : "/workspaces",
    );
  }
}
