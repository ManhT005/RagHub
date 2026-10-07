import { DatePipe } from "@angular/common";
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
import { RouterLink } from "@angular/router";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { finalize } from "rxjs";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzDropDownModule } from "ng-zorro-antd/dropdown";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzPopconfirmModule } from "ng-zorro-antd/popconfirm";
import { NzTableModule } from "ng-zorro-antd/table";
import { NzTagModule } from "ng-zorro-antd/tag";

import { apiError } from "../../core/api/api-error";
import { Chatbot, RaghubApiService } from "../../core/raghub-api.service";
import { WorkspaceContextStore } from "../../core/workspace-context/workspace-context.store";

@Component({
  selector: "raghub-workspace-chatbots",
  imports: [
    DatePipe,
    FormsModule,
    RouterLink,
    NzAlertModule,
    NzButtonModule,
    NzDropDownModule,
    NzInputModule,
    NzPopconfirmModule,
    NzTableModule,
    NzTagModule,
  ],
  templateUrl: "./workspace-chatbots.component.html",
  styleUrl: "./workspace-chatbots.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceChatbotsComponent {
  protected readonly context = inject(WorkspaceContextStore);
  protected readonly bots = signal<Chatbot[]>([]);
  protected readonly loading = signal(false);
  protected readonly deletingId = signal("");
  protected readonly error = signal("");
  protected readonly search = signal("");
  protected readonly status = signal<"" | "published" | "draft">("");
  protected readonly sort = signal<"newest" | "oldest" | "name">("newest");
  protected readonly filtered = computed(() =>
    this.bots()
      .filter((bot) =>
        bot.name.toLowerCase().includes(this.search().trim().toLowerCase()),
      )
      .filter(
        (bot) =>
          !this.status() ||
          (this.status() === "published" ? bot.published : !bot.published),
      )
      .sort((left, right) =>
        this.sort() === "name"
          ? left.name.localeCompare(right.name)
          : this.sort() === "oldest"
            ? left.created_at.localeCompare(right.created_at)
            : right.created_at.localeCompare(left.created_at),
      ),
  );

  private readonly api = inject(RaghubApiService);
  private readonly destroyRef = inject(DestroyRef);
  private workspaceId = "";

  constructor() {
    effect(() => {
      const id = this.context.workspace()?.id ?? "";
      if (id === this.workspaceId) return;
      this.workspaceId = id;
      this.bots.set([]);
      this.error.set("");
      if (id) untracked(() => this.load());
    });
  }

  protected load() {
    if (!this.workspaceId) return;
    this.loading.set(true);
    this.api
      .chatbots(this.workspaceId)
      .pipe(
        finalize(() => this.loading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (bots) => this.bots.set(bots),
        error: (error) => this.error.set(apiError(error)),
      });
  }

  protected delete(bot: Chatbot) {
    if (!this.context.can("workspace.edit") || this.deletingId()) return;
    this.deletingId.set(bot.id);
    this.error.set("");
    this.api
      .deleteChatbot(bot.id)
      .pipe(
        finalize(() => this.deletingId.set("")),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => this.load(),
        error: (error) => this.error.set(apiError(error)),
      });
  }
}
