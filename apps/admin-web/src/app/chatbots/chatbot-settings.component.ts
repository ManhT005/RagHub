import {
  ChangeDetectionStrategy,
  Component,
  inject,
  signal,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
import { ActivatedRoute, RouterLink } from "@angular/router";
import { RaghubApiService } from "../core/raghub-api.service";

@Component({
  selector: "raghub-chatbot-settings",
  imports: [FormsModule, RouterLink],
  templateUrl: "./chatbot-settings.component.html",
  styleUrl: "./chatbot-settings.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChatbotSettingsComponent {
  private readonly api = inject(RaghubApiService);
  private readonly route = inject(ActivatedRoute);
  readonly notice = signal("");
  readonly code = signal("");
  readonly loading = signal(true);
  id = "";
  name = "";
  published = false;
  origins = location.origin;
  primaryColor = "#1463ff";
  title = "RagHub Assistant";
  greeting = "Xin chào! Tôi có thể giúp gì cho bạn?";
  constructor() {
    this.id = this.route.snapshot.paramMap.get("id") || "";
    this.api.chatbot(this.id).subscribe({
      next: (bot) => {
        this.name = bot.name;
        this.published = bot.published;
        this.origins = bot.allowed_origins?.join("\n") || location.origin;
        this.primaryColor = bot.embed_primary_color || this.primaryColor;
        this.title = bot.embed_title || bot.name;
        this.greeting = bot.embed_greeting || this.greeting;
        this.loading.set(false);
        if (bot.published) this.loadCode();
      },
      error: () => {
        this.notice.set("Không thể tải chatbot.");
        this.loading.set(false);
      },
    });
  }
  publish() {
    const allowed_origins = this.origins
      .split(/\n|,/)
      .map((value) => value.trim())
      .filter(Boolean);
    this.api
      .publishEmbed(this.id, {
        allowed_origins,
        primary_color: this.primaryColor,
        title: this.title.trim(),
        greeting: this.greeting.trim(),
      })
      .subscribe({
        next: (result) => {
          this.published = true;
          this.code.set(result.code);
          this.notice.set(
            "Đã xuất bản. Hãy lưu embed key ngay — key chỉ hiện một lần.",
          );
        },
        error: (error) =>
          this.notice.set(
            error?.error?.error?.message || "Không thể xuất bản chatbot.",
          ),
      });
  }
  rotate() {
    this.api.rotateEmbedKey(this.id).subscribe({
      next: (result) => {
        this.code.set(result.code);
        this.notice.set("Đã tạo embed key mới. Key cũ không còn hoạt động.");
      },
      error: () => this.notice.set("Không thể xoay embed key."),
    });
  }
  loadCode() {
    this.api
      .embedCode(this.id)
      .subscribe({
        next: (result) => this.code.set(result.code),
        error: () =>
          this.notice.set(
            "Không thể lấy mã nhúng. Key chỉ có thể hiện lại khi xoay key.",
          ),
      });
  }
  async copy() {
    if (this.code()) await navigator.clipboard?.writeText(this.code());
    this.notice.set("Đã sao chép mã nhúng.");
  }
}
