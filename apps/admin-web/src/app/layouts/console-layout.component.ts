import { ChangeDetectionStrategy, Component, computed, inject, signal } from "@angular/core";
import { RouterLink, RouterLinkActive, RouterOutlet } from "@angular/router";
import { NzIconModule } from "ng-zorro-antd/icon";
import { NzLayoutModule } from "ng-zorro-antd/layout";
import { NzMenuModule } from "ng-zorro-antd/menu";

import { session } from "../core/api-auth.interceptor";
import { Organization, RaghubApiService } from "../core/raghub-api.service";

@Component({
  selector: "raghub-console-layout",
  imports: [
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    NzIconModule,
    NzLayoutModule,
    NzMenuModule,
  ],
  templateUrl: "./console-layout.component.html",
  styleUrl: "./console-layout.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ConsoleLayoutComponent {
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly isAdmin = computed(() => {
    const currentId = session.organizationId;
    const current = this.organizations().find((item) => item.id === currentId)
      ?? this.organizations()[0];
    return current?.role === "ADMIN";
  });

  private readonly api = inject(RaghubApiService);

  constructor() {
    this.api.organizations().subscribe({
      next: (organizations) => this.organizations.set(organizations),
      error: () => this.organizations.set([]),
    });
  }
}
