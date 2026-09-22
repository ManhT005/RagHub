import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { session } from '../core/api-auth.interceptor';
import { Membership, Organization, RaghubApiService, Workspace } from '../core/raghub-api.service';

@Component({
  selector: 'raghub-workspaces',
  imports: [FormsModule],
  templateUrl: './workspaces.component.html',
  styleUrl: './workspaces.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspacesComponent {
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
      error: () => this.error.set('Sign in first, then select an organization.'),
    });
  }

  protected changeOrganization(): void {
    session.organizationId = this.selectedOrganization || null;
    if (!this.selectedOrganization) return;
    this.api.workspaces().subscribe({ next: (items) => this.workspaces.set(items), error: () => this.error.set('Could not load workspaces.') });
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
      error: () => this.error.set('Could not create organization. The slug may already be in use.'),
    });
  }

  protected saveMember(): void {
    if (!this.selectedOrganization) return;
    this.api.saveMember(this.selectedOrganization, this.memberEmail, this.memberRole).subscribe({
      next: (member) => {
        this.members.update((items) => [...items.filter((item) => item.user_id !== member.user_id), member]);
        this.memberEmail = '';
      },
      error: () => this.error.set('Could not add this member. They must register first.'),
    });
  }

  protected removeMember(member: Membership): void {
    if (!this.selectedOrganization || member.role === 'OWNER') return;
    this.api.deleteMember(this.selectedOrganization, member.user_id).subscribe({
      next: () => this.members.update((items) => items.filter((item) => item.user_id !== member.user_id)),
      error: () => this.error.set('Could not remove member.'),
    });
  }

  protected create(): void {
    this.api.createWorkspace(this.name, this.slug).subscribe({
      next: (workspace) => { this.workspaces.update((items) => [...items, workspace]); this.name = ''; this.slug = ''; },
      error: () => this.error.set('Could not create workspace. The slug may already be in use.'),
    });
  }
}
