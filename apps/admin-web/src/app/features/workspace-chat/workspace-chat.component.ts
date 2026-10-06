import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  untracked,
  DestroyRef,
  OnDestroy,
  inject,
  signal,
} from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { FormsModule } from "@angular/forms";
import { RouterLink } from "@angular/router";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzModalModule } from "ng-zorro-antd/modal";
import { Subscription, finalize } from "rxjs";
import {
  Chatbot,
  ChatStreamEvent,
  RaghubApiService,
} from "../../core/raghub-api.service";
import { WorkspaceContextStore } from "../../core/workspace-context/workspace-context.store";
import { apiError } from "../../core/api/api-error";
import { chatError } from "../../core/api/chat-error";
interface Message {
  role: "user" | "assistant";
  text: string;
  citations?: { document_name?: string; page?: number }[];
}
@Component({
  selector: "raghub-workspace-chat",
  imports: [
    FormsModule,
    RouterLink,
    NzButtonModule,
    NzInputModule,
    NzAlertModule,
    NzModalModule,
  ],
  templateUrl: "./workspace-chat.component.html",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceChatComponent implements OnDestroy {
  protected readonly context = inject(WorkspaceContextStore);
  protected readonly bots = signal<Chatbot[]>([]);
  protected readonly loading = signal(false);
  protected readonly streaming = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal("");
  protected readonly messages = signal<Message[]>([]);
  protected readonly editorOpen = signal(false);
  protected selected = "";
  protected question = "";
  protected name = "";
  protected prompt =
    "Trả lời dựa trên tài liệu được cung cấp. Nếu không có thông tin, hãy nói rõ.";
  private readonly api = inject(RaghubApiService);
  private readonly destroyRef = inject(DestroyRef);
  private conversationId: string | null = null;
  private controller?: AbortController;
  private loadRequest?: Subscription;
  constructor() {
    const workspaceId = computed(() => this.context.workspace()?.id);
    effect(() => {
      const id = workspaceId();
      this.loadRequest?.unsubscribe();
      untracked(() => this.reset());
      this.bots.set([]);
      this.selected = "";
      if (id) untracked(() => this.load());
    });
  }
  protected load() {
    this.loading.set(true);
    this.loadRequest?.unsubscribe();
    this.loadRequest = this.api
      .chatbots(this.context.workspace()!.id)
      .pipe(
        finalize(() => this.loading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (items) => {
          this.bots.set(items);
          if (!items.some((bot) => bot.id === this.selected))
            this.selected = items[0]?.id ?? "";
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected selectedBot() {
    return this.bots().find((bot) => bot.id === this.selected);
  }
  protected reset() {
    this.controller?.abort();
    this.streaming.set(false);
    this.conversationId = null;
    this.messages.set([]);
    this.error.set("");
  }
  protected send() {
    if (
      !this.question.trim() ||
      !this.selected ||
      this.streaming() ||
      !this.context.can("chat.use")
    )
      return;
    const question = this.question.trim();
    this.question = "";
    this.error.set("");
    this.streaming.set(true);
    this.messages.update((items) => [
      ...items,
      { role: "user", text: question },
      { role: "assistant", text: "" },
    ]);
    this.controller = new AbortController();
    void this.api
      .streamChat(
        this.selected,
        { message: question, conversation_id: this.conversationId },
        (event) => this.handle(event),
        this.controller.signal,
      )
      .finally(() => this.streaming.set(false));
  }
  private handle(event: ChatStreamEvent) {
    if (event.event === "conversation")
      this.conversationId =
        typeof event.data["conversation_id"] === "string"
          ? event.data["conversation_id"]
          : null;
    if (event.event === "clarification" && typeof event.data["message"] === "string")
      this.messages.update((items) =>
        items.map((item, index) =>
          index === items.length - 1
            ? { ...item, text: event.data["message"] as string }
            : item,
        ),
      );
    if (event.event === "token" && typeof event.data["text"] === "string")
      this.messages.update((items) =>
        items.map((item, index) =>
          index === items.length - 1
            ? { ...item, text: item.text + event.data["text"] }
            : item,
        ),
      );
    if (event.event === "citations" && Array.isArray(event.data["citations"]))
      this.messages.update((items) =>
        items.map((item, index) =>
          index === items.length - 1
            ? {
                ...item,
                citations: event.data["citations"] as Message["citations"],
              }
            : item,
        ),
      );
    if (event.event === "error")
      this.error.set(chatError(event.data));
  }
  protected create() {
    if (
      !this.name.trim() ||
      this.saving() ||
      !this.context.can("workspace.edit")
    )
      return;
    this.saving.set(true);
    this.error.set("");
    this.api
      .createChatbot(this.context.workspace()!.id, {
        name: this.name.trim(),
        system_prompt: this.prompt,
        retrieval_limit: 5,
        published: false,
      })
      .pipe(
        finalize(() => this.saving.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (bot) => {
          this.selected = bot.id;
          this.editorOpen.set(false);
          this.load();
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  ngOnDestroy() {
    this.controller?.abort();
  }
}
