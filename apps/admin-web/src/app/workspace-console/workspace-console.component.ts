import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { session } from '../core/api-auth.interceptor';
import { Organization, RaghubApiService, Workspace } from '../core/raghub-api.service';

@Component({
  selector: 'raghub-workspace-console',
  imports: [FormsModule, RouterLink],
  templateUrl: './workspace-console.component.html',
  styleUrl: './workspace-console.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceConsoleComponent {
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly error = signal('');
  protected selectedOrganization = session.organizationId ?? '';
  protected selectedWorkspace = '';
  private readonly api = inject(RaghubApiService);

  constructor() {
    this.api.organizations().subscribe({
      next: (items) => {
        this.organizations.set(items);
        if (!this.selectedOrganization && items[0]) this.selectedOrganization = items[0].id;
        this.changeOrganization();
      },
      error: () => this.error.set('Hãy đăng nhập và chọn một tổ chức trước khi mở workspace.'),
    });
  }

  protected changeOrganization(): void {
    session.organizationId = this.selectedOrganization || null;
    this.workspaces.set([]);
    this.selectedWorkspace = '';
    if (!this.selectedOrganization) return;
    this.api.workspaces().subscribe({
      next: (items) => {
        this.workspaces.set(items);
        this.selectedWorkspace = items[0]?.id ?? '';
      },
      error: () => this.error.set('Không thể tải danh sách không gian làm việc.'),
    });
  }
}
