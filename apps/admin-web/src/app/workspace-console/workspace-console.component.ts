import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { session } from '../core/api-auth.interceptor';
import {
  Chatbot,
  DocumentItem,
  Organization,
  ProviderConfig,
  RaghubApiService,
  Workspace,
} from '../core/raghub-api.service';

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
  protected readonly providers = signal<ProviderConfig[]>([]);
  protected readonly documents = signal<DocumentItem[]>([]);
  protected readonly bots = signal<Chatbot[]>([]);
  protected readonly selectedBot = signal<Chatbot | null>(null);
  protected readonly hasReadyDocument = computed(() =>
    this.documents().some((item) => item.status === 'READY'),
  );
  protected readonly hasChatProvider = computed(() =>
    this.providers().some((item) => item.capability === 'CHAT' && item.enabled),
  );
  protected readonly hasPublishedBot = computed(() => Boolean(this.selectedBot()?.published));
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
        this.changeWorkspace();
      },
      error: () => this.error.set('Không thể tải danh sách không gian làm việc.'),
    });
  }

  protected changeWorkspace(): void {
    this.providers.set([]);
    this.documents.set([]);
    this.bots.set([]);
    this.selectedBot.set(null);
    if (!this.selectedOrganization || !this.selectedWorkspace) return;
    this.api.providers(this.selectedOrganization).subscribe({
      next: (items) => this.providers.set(items),
      error: () => this.error.set('Không thể tải cấu hình AI của tổ chức.'),
    });
    this.api.documents(this.selectedWorkspace).subscribe({
      next: (items) => this.documents.set(items),
      error: () => this.error.set('Không thể tải tài liệu của workspace.'),
    });
    this.api.chatbots(this.selectedWorkspace).subscribe({
      next: (items) => {
        this.bots.set(items);
        this.selectedBot.set(items.find((bot) => bot.published) ?? items[0] ?? null);
      },
      error: () => this.error.set('Không thể tải chatbot của workspace.'),
    });
  }
}
