import {
  ChangeDetectionStrategy,
  Component,
  inject,
  signal,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
import { HttpErrorResponse } from "@angular/common/http";
import { Router } from "@angular/router";

import { RaghubApiService } from "../core/raghub-api.service";
import { session } from "../core/api-auth.interceptor";

@Component({
  selector: "raghub-auth",
  imports: [FormsModule],
  templateUrl: "./auth.component.html",
  styleUrl: "./auth.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AuthComponent {
  protected email = "";
  protected password = "";
  protected registerMode = false;
  protected readonly error = signal("");
  private readonly api = inject(RaghubApiService);
  private readonly router = inject(Router);

  protected toggleMode(): void {
    this.registerMode = !this.registerMode;
    this.error.set("");
  }

  protected submit(): void {
    this.error.set("");
    const registering = this.registerMode;
    const request = registering
      ? this.api.register(this.email, this.password)
      : this.api.login(this.email, this.password);
    request.subscribe({
      next: ({ access_token }) => {
        session.accessToken = access_token;
        this.router.navigateByUrl("/workspaces");
      },
      error: (response: HttpErrorResponse) => {
        if (registering) {
          this.error.set(
            response.error?.error?.code === "EMAIL_ALREADY_REGISTERED"
              ? "Email này đã được đăng ký. Hãy đăng nhập."
              : "Không thể tạo tài khoản. Vui lòng thử lại.",
          );
        } else {
          this.error.set(
            "Không thể đăng nhập. Hãy kiểm tra email và mật khẩu.",
          );
        }
      },
    });
  }
}
