import { DatePipe } from "@angular/common";
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  effect,
  inject,
  signal,
  output,
  untracked,
} from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { FormsModule } from "@angular/forms";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzModalModule } from "ng-zorro-antd/modal";
import { NzProgressModule } from "ng-zorro-antd/progress";
import { NzTagModule } from "ng-zorro-antd/tag";
import { NzInputModule } from "ng-zorro-antd/input";
import {
  EMPTY,
  Subscription,
  catchError,
  exhaustMap,
  finalize,
  takeWhile,
  switchMap,
  timer,
} from "rxjs";
import {
  ProviderApiService,
  RegistryModel,
  selectableModel,
} from "../../core/api/provider-api.service";
import {
  EmbeddingPreview,
  ReindexJob,
  REINDEX_TERMINAL,
  WorkspaceApiService,
} from "../../core/api/workspace-api.service";
import { WorkspaceContextStore } from "../../core/workspace-context/workspace-context.store";
import { apiError } from "../../core/api/api-error";
import { ProviderLogoComponent } from "../../shared/provider-logo/provider-logo.component";
import { shortModelName } from "../../core/provider-brand/provider-brand.registry";

@Component({
  selector: "raghub-embedding-profile",
  imports: [
    NzInputModule,
    ProviderLogoComponent,
    DatePipe,
    FormsModule,
    NzButtonModule,
    NzAlertModule,
    NzModalModule,
    NzProgressModule,
    NzTagModule,
  ],
  templateUrl: "./embedding-profile.component.html",
  styleUrl: "./embedding-profile.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EmbeddingProfileComponent {
  readonly dialogClosed = output<void>();
  protected readonly shortModelName = shortModelName;
  protected readonly modelQuery = signal("");
  protected readonly modelCategory = signal("");
  protected readonly modelProvider = signal("");
  protected filteredModels() {
    return this.models().filter(
      (model) =>
        `${model.model} ${model.provider_name}`
          .toLowerCase()
          .includes(this.modelQuery().toLowerCase()) &&
        (!this.modelProvider() ||
          model.provider_catalog_id === this.modelProvider()) &&
        (!this.modelCategory() ||
          this.category(model.provider_catalog_id) === this.modelCategory()),
    );
  }
  protected providerOptions() {
    return this.models().filter(
      (model, index, items) =>
        items.findIndex(
          (item) => item.provider_catalog_id === model.provider_catalog_id,
        ) === index,
    );
  }
  protected category(catalogId: string | null) {
    return catalogId === "sentence-transformer" || catalogId === "ollama"
      ? "Local"
      : catalogId === "compatible" || !catalogId
        ? "Custom"
        : "Cloud";
  }
  protected selectedModel() {
    return this.models().find((model) => model.id === this.selected);
  }
  protected close() {
    if (this.busy()) return;
    this.open.set(false);
  }
  protected readonly context = inject(WorkspaceContextStore);
  protected readonly open = signal(false);
  protected readonly busy = signal(false);
  protected readonly loading = signal(false);
  protected readonly models = signal<RegistryModel[]>([]);
  protected readonly preview = signal<EmbeddingPreview | null>(null);
  protected readonly job = signal<ReindexJob | null>(null);
  protected readonly error = signal("");
  protected selected = "";
  protected confirmed = false;
  private readonly api = inject(WorkspaceApiService);
  private readonly providers = inject(ProviderApiService);
  private readonly destroyRef = inject(DestroyRef);
  private polling?: Subscription;
  private pollKey = "";
  constructor() {
    effect(() => {
      const workspace = this.context.workspace();

      if (!this.context.can("ai.change_embedding")) {
        this.open.set(false);
        this.preview.set(null);
      }
      const key = workspace
        ? `${workspace.id}:${workspace.reindex_job_id}`
        : "";
      if (key === this.pollKey) return;
      this.open.set(false);
      this.preview.set(null);
      this.confirmed = false;
      this.selected = "";
      this.pollKey = key;
      this.polling?.unsubscribe();
      this.job.set(null);
      if (!workspace?.reindex_job_id) return;
      const workspaceId = workspace.id,
        jobId = workspace.reindex_job_id;
      this.polling = timer(0, 3000)
        .pipe(
          exhaustMap(() => this.api.reindexJob(workspaceId, jobId)),
          takeWhile((job) => !REINDEX_TERMINAL.includes(job.status), true),
          catchError((error) => {
            this.error.set(apiError(error));
            return EMPTY;
          }),
          takeUntilDestroyed(this.destroyRef),
        )
        .subscribe((job) => {
          this.job.set(job);
          if (REINDEX_TERMINAL.includes(job.status))
            untracked(() =>
              this.context
                .refresh()
                .pipe(takeUntilDestroyed(this.destroyRef))
                .subscribe({
                  error: (error) => this.error.set(apiError(error)),
                }),
            );
        });
    });
  }
  choose() {
    if (!this.context.can("ai.change_embedding") || this.busy()) return;
    this.selected = "";
    this.confirmed = false;
    this.preview.set(null);
    this.error.set("");
    this.modelQuery.set("");
    this.modelCategory.set("");
    this.modelProvider.set("");
    this.open.set(true);
    this.loading.set(true);
    this.providers
      .workspaceModels(this.context.workspace()!.id)
      .pipe(
        finalize(() => this.loading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (items) => this.models.set(items.filter(selectableModel)),
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected selectionChanged() {
    this.preview.set(null);
    this.confirmed = false;
  }
  protected review() {
    if (!this.selected || this.busy()) return;
    this.busy.set(true);
    this.error.set("");
    this.api
      .preview(this.context.workspace()!.id, this.selected)
      .pipe(
        finalize(() => this.busy.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (value) => this.preview.set(value),
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected apply() {
    const preview = this.preview();
    if (
      !this.context.can("ai.change_embedding") ||
      !preview ||
      preview.target_model.id !== this.selected ||
      !this.confirmed ||
      this.busy()
    )
      return;
    this.busy.set(true);
    this.error.set("");
    this.api
      .changeEmbedding(this.context.workspace()!.id, this.selected)
      .pipe(
        switchMap(() => this.context.refresh()),
        finalize(() => this.busy.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => {
          this.open.set(false);
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected retry() {
    const jobId = this.context.workspace()?.reindex_job_id;
    if (!jobId || this.busy() || !this.context.can("ai.change_embedding"))
      return;
    this.busy.set(true);
    this.error.set("");
    this.api
      .retryReindex(jobId)
      .pipe(
        finalize(() => this.busy.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => {
          this.pollKey = "";
          this.refresh();
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected retryable() {
    return ["FAILED", "QUEUE_FAILED"].includes(
      this.job()?.status ?? this.context.workspace()?.reindex_status ?? "",
    );
  }
  protected migrating() {
    const status =
      this.job()?.status ?? this.context.workspace()?.reindex_status;
    return !!status && !REINDEX_TERMINAL.includes(status);
  }
  protected progress() {
    const job = this.job();
    return job?.total_documents
      ? Math.min(
          100,
          Math.round((job.processed_documents / job.total_documents) * 100),
        )
      : 0;
  }
  private refresh() {
    this.context
      .refresh()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({ error: (error) => this.error.set(apiError(error)) });
  }
}
