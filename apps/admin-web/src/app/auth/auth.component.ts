import {
  ChangeDetectionStrategy,
  Component,
  inject,
  signal,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
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

  protected submit(): void {
    this.error.set("");
    const request = this.registerMode
      ? this.api.register(this.email, this.password)
      : this.api.login(this.email, this.password);
    request.subscribe({
      next: ({ access_token }) => {
        session.accessToken = access_token;
        this.router.navigateByUrl("/workspaces");
      },
      error: () =>
        this.error.set(
          "Could not sign in. Check your credentials and try again.",
        ),
    });
  }
}
