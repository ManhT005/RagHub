import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { session } from '../core/api-auth.interceptor';
import { Membership, Organization, RaghubApiService, Workspace } from '../core/raghub-api.service';

@Component({
  selector: 'raghub-workspaces',
  imports: [FormsModule, RouterLink],
  templateUrl: './workspaces.component.html',
  styleUrl: './workspaces.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspacesComponent {
  protected readonly roleLabel = (role: string): string => ({
    OWNER: 'Chủ sở hữu',
    ADMIN: 'Quản trị viên',
    EDITOR: 'Biên tập viên',
    VIEWER: 'Người xem',
  })[role] ?? role;
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly members = signal<Membership[]>([]);
  protected readonly error = signal('');
  protected selectedOrganization = session.organizationId ?? '';
  protected name = '';
  protected slug = '';
  protected organizationName = '';
  protected organizationSlug = '';
  protected memberEmail = '';
  protected memberRole: Membership['role'] = 'EDITOR';
  private readonly api = inject(RaghubApiService);

  constructor() { this.loadOrganizations(); }

  protected loadOrganizations(): void {
    this.api.organizations().subscribe({
      next: (organizations) => {
        this.organizations.set(organizations);
        if (!this.selectedOrganization && organizations[0]) this.selectedOrganization = organizations[0].id;
        this.changeOrganization();
      },
      error: () => this.error.set('Hãy đăng nhập, sau đó chọn một tổ chức.'),
    });
  }

  protected changeOrganization(): void {
    session.organizationId = this.selectedOrganization || null;
    if (!this.selectedOrganization) return;
    this.api.workspaces().subscribe({ next: (items) => this.workspaces.set(items), error: () => this.error.set('Không thể tải danh sách không gian làm việc.') });
    this.api.members(this.selectedOrganization).subscribe({ next: (items) => this.members.set(items), error: () => this.members.set([]) });
  }

  protected createOrganization(): void {
    this.api.createOrganization(this.organizationName, this.organizationSlug).subscribe({
      next: (organization) => {
        this.organizations.update((items) => [...items, organization]);
        this.selectedOrganization = organization.id;
        this.organizationName = '';
        this.organizationSlug = '';
        this.changeOrganization();
      },
      error: () => this.error.set('Không thể tạo tổ chức. Mã định danh có thể đã được sử dụng.'),
    });
  }

  protected saveMember(): void {
    if (!this.selectedOrganization) return;
    this.api.saveMember(this.selectedOrganization, this.memberEmail, this.memberRole).subscribe({
      next: (member) => {
        this.members.update((items) => [...items.filter((item) => item.user_id !== member.user_id), member]);
        this.memberEmail = '';
      },
      error: () => this.error.set('Không thể thêm thành viên. Người này cần đăng ký tài khoản trước.'),
    });
  }

  protected removeMember(member: Membership): void {
    if (!this.selectedOrganization || member.role === 'OWNER') return;
    this.api.deleteMember(this.selectedOrganization, member.user_id).subscribe({
      next: () => this.members.update((items) => items.filter((item) => item.user_id !== member.user_id)),
      error: () => this.error.set('Không thể xóa thành viên.'),
    });
  }

  protected create(): void {
    this.api.createWorkspace(this.name, this.slug).subscribe({
      next: (workspace) => { this.workspaces.update((items) => [...items, workspace]); this.name = ''; this.slug = ''; },
      error: () => this.error.set('Không thể tạo không gian làm việc. Mã định danh có thể đã được sử dụng.'),
    });
  }
}
