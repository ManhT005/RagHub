import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  signal,
} from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { FormsModule } from "@angular/forms";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { finalize } from "rxjs";
import {
  ProviderApiService,
  RegistryModel,
  selectableModel,
} from "../../core/api/provider-api.service";
import { WorkspaceApiService } from "../../core/api/workspace-api.service";
import { WorkspaceContextStore } from "../../core/workspace-context/workspace-context.store";
import { apiError } from "../../core/api/api-error";
import { EmbeddingProfileComponent } from "./embedding-profile.component";
@Component({
  selector: "raghub-workspace-ai",
  imports: [
    FormsModule,
    NzButtonModule,
    NzAlertModule,
    EmbeddingProfileComponent,
  ],
  template: `<header class="page-heading">
      <div>
        <span class="eyebrow">WORKSPACE / AI</span>
        <h1>Cài đặt AI</h1>
        <p>Chọn model cho tìm kiếm và hội thoại của workspace.</p>
      </div>
    </header>
    <raghub-embedding-profile />
    <section class="surface" style="margin-top:24px">
      <h2>Chat model</h2>
      <p class="muted">{{ currentChat() }}</p>
      @if (context.can("workspace.edit")) {
        <label
          >Model<select [(ngModel)]="selected" [disabled]="busy()">
            <option value="">Chọn model khả dụng</option>
            @for (model of models(); track model.id) {
              <option [value]="model.id">
                {{ model.display_name ?? model.model }} ·
                {{ model.provider_name }}
              </option>
            }
          </select></label
        ><button
          nz-button
          nzType="primary"
          [disabled]="!selected"
          [nzLoading]="busy()"
          (click)="save()"
        >
          Lưu chat model
        </button>
      }
      @if (error()) {
        <nz-alert nzType="error" [nzMessage]="error()" nzShowIcon />
      }
      @if (notice()) {
        <nz-alert nzType="success" [nzMessage]="notice()" nzShowIcon />
      }
    </section>`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceAiComponent {
  protected readonly context = inject(WorkspaceContextStore);
  protected readonly models = signal<RegistryModel[]>([]);
  protected readonly error = signal("");
  protected readonly notice = signal("");
  protected readonly busy = signal(false);
  protected selected = "";
  private readonly api = inject(WorkspaceApiService);
  private readonly providers = inject(ProviderApiService);
  private readonly destroyRef = inject(DestroyRef);
  constructor() {
    this.providers
      .workspaceModels(this.context.workspace()!.id, "CHAT")
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (items) => {
          this.models.set(items.filter(selectableModel));
          this.selected = this.context.workspace()?.chat_provider_id ?? "";
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected currentChat() {
    const model = this.models().find(
      (item) => item.id === this.context.workspace()?.chat_provider_id,
    );
    return model
      ? `${model.model} · ${model.provider_name}`
      : this.context.workspace()?.chat_provider_id
        ? "Model đã gắn hiện không khả dụng trong danh sách chọn mới."
        : "Chưa cấu hình chat model.";
  }
  protected save() {
    if (!this.selected || this.busy() || !this.context.can("workspace.edit"))
      return;
    this.busy.set(true);
    this.error.set("");
    this.notice.set("");
    this.api
      .changeChat(this.context.workspace()!.id, this.selected)
      .pipe(
        finalize(() => this.busy.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => {
          this.notice.set("Đã cập nhật chat model.");
          this.context
            .refresh()
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({ error: (error) => this.error.set(apiError(error)) });
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
}
