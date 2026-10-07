import { ChangeDetectionStrategy, Component, DestroyRef, EventEmitter, Input, Output, inject, signal } from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { FormsModule } from "@angular/forms";
import { ActivatedRoute, RouterLink } from "@angular/router";
import { finalize } from "rxjs";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzPopconfirmModule } from "ng-zorro-antd/popconfirm";
import { Chatbot, EmbedCode, RaghubApiService } from "../core/raghub-api.service";
import { DEFAULT_WIDGET_COLOR, parseWidgetOrigins, validWidgetColor, widgetForeground } from "./widget-settings.utils";

@Component({
  selector: "raghub-chatbot-settings",
  imports: [FormsModule, RouterLink, NzButtonModule, NzInputModule, NzPopconfirmModule],
  templateUrl: "./chatbot-settings.component.html",
  styleUrl: "./chatbot-settings.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChatbotSettingsComponent {
  private readonly api = inject(RaghubApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private bot: Chatbot | null = null;
  private embedVersion = 0;
  @Input() set chatbot(bot: Chatbot | null) { if (bot && bot.id !== this.id) this.initialize(bot); }
  @Output() readonly saved = new EventEmitter<Chatbot>();
  @Output() readonly busyChange = new EventEmitter<boolean>();
  readonly embedded = signal(false);
  readonly notice = signal("");
  readonly error = signal("");
  readonly code = signal("");
  readonly rawKey = signal("");
  readonly publicBaseUrl = signal("");
  readonly scriptSrc = signal("");
  readonly hasEmbedKey = signal(false);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly previewDevice = signal<"desktop" | "mobile">("desktop");
  id = "";
  name = "";
  published = false;
  origins = location.origin;
  primaryColor = DEFAULT_WIDGET_COLOR;
  title = "RagHub Assistant";
  greeting = "Xin chào! Tôi có thể giúp gì cho bạn?";
  logoData: string | null = null;

  constructor() {
    const id = this.route.snapshot.paramMap?.get("id");
    if (!id) { this.embedded.set(true); return; }
    this.api.chatbot(id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (bot) => this.initialize(bot),
      error: () => { this.error.set("Không thể tải chatbot."); this.loading.set(false); },
    });
  }
  private initialize(bot: Chatbot) {
    this.bot = bot;
    this.id = bot.id;
    this.name = bot.name;
    this.published = bot.published;
    this.origins = bot.allowed_origins?.join("\n") || location.origin;
    this.primaryColor = bot.embed_primary_color || DEFAULT_WIDGET_COLOR;
    this.title = bot.embed_title || bot.name;
    this.greeting = bot.embed_greeting || this.greeting;
    this.logoData = bot.embed_logo_data || null;
    this.code.set(""); this.rawKey.set(""); this.hasEmbedKey.set(false);
    this.publicBaseUrl.set(""); this.scriptSrc.set("");
    this.loading.set(false);
    this.loadCode();
  }
  colorValid() { return validWidgetColor(this.primaryColor); }
  previewColor() { return this.colorValid() ? this.primaryColor : DEFAULT_WIDGET_COLOR; }
  previewForeground() { return widgetForeground(this.primaryColor); }
  parsedOrigins() { return parseWidgetOrigins(this.origins); }
  valid() { return this.colorValid() && !this.parsedOrigins().error && !!this.title.trim() && !!this.greeting.trim(); }
  removeOrigin(origin: string) { this.origins = this.parsedOrigins().origins.filter((v) => v !== origin).join("\n"); }
  addCurrentOrigin() {
    const values = this.origins.split(/\n|,/).map((v) => v.trim()).filter(Boolean);
    if (!values.includes(location.origin)) values.push(location.origin);
    this.origins = values.join("\n");
  }
  selectLogo(file: File | undefined) {
    if (!file) return;
    if (!/^image\/(png|jpeg|webp)$/.test(file.type) || file.size > 1024 * 1024) {
      this.error.set("Logo phải là ảnh PNG, JPG hoặc WebP, tối đa 1 MB."); return;
    }
    const reader = new FileReader();
    reader.onload = () => { this.logoData = String(reader.result); this.error.set(""); };
    reader.readAsDataURL(file);
  }
  dropLogo(event: DragEvent) { event.preventDefault(); this.selectLogo(event.dataTransfer?.files[0]); }
  clearLogo() { this.logoData = null; }
  localPublicUrl() {
    try { return ["localhost", "127.0.0.1", "[::1]"].includes(new URL(this.publicBaseUrl()).hostname); }
    catch { return false; }
  }
  demoUrl() {
    if (!this.rawKey() || !this.publicBaseUrl()) return null;
    const url = new URL("/demo/", this.publicBaseUrl());
    // Fragment avoids sending the show-once key in HTTP access logs.
    url.hash = new URLSearchParams({ key: this.rawKey(), api: this.publicBaseUrl() }).toString();
    return url.toString();
  }
  private setBusy(value: boolean) { this.busy.set(value); this.busyChange.emit(value); }
  private acceptEmbed(result: EmbedCode, replace = false) {
    this.publicBaseUrl.set(result.public_base_url);
    this.scriptSrc.set(result.script_src);
    this.hasEmbedKey.set(result.has_embed_key);
    if (result.code || replace) this.code.set(result.code ?? "");
    if (result.key || replace) this.rawKey.set(result.key ?? "");
  }
  publish() {
    if (!this.valid() || this.busy() || !this.bot) return;
    const payload = { allowed_origins: this.parsedOrigins().origins, primary_color: this.primaryColor,
      title: this.title.trim(), greeting: this.greeting.trim(), logo_data: this.logoData };
    this.embedVersion++;
    this.error.set(""); this.notice.set(""); this.setBusy(true);
    this.api.publishEmbed(this.id, payload).pipe(
      finalize(() => this.setBusy(false)), takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: (result) => {
        this.published = true; this.origins = payload.allowed_origins.join("\n");
        this.acceptEmbed(result);
        this.bot = { ...this.bot!, published: true, allowed_origins: payload.allowed_origins,
          embed_primary_color: payload.primary_color, embed_title: payload.title, embed_greeting: payload.greeting, embed_logo_data: payload.logo_data };
        this.saved.emit(this.bot);
        this.notice.set(result.key ? "Đã xuất bản. Sao chép mã nhúng ngay; key chỉ hiển thị một lần." : "Đã lưu cấu hình. Mã nhúng đang dùng trên website vẫn hoạt động.");
      },
      error: (error) => this.error.set(this.embedError(error, "Không thể lưu cấu hình nhúng.")),
    });
  }
  rotate() {
    if (!this.published || this.busy()) return;
    this.embedVersion++;
    this.error.set(""); this.notice.set(""); this.setBusy(true);
    this.api.rotateEmbedKey(this.id).pipe(
      finalize(() => this.setBusy(false)), takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: (result) => { this.acceptEmbed(result, true); this.notice.set("Đã tạo key mới. Thay script trên website; key cũ đã ngừng hoạt động."); },
      error: (error) => this.error.set(this.embedError(error, "Không thể tạo embed key mới.")),
    });
  }
  loadCode() {
    const id = this.id;
    const version = this.embedVersion;
    this.api.embedCode(id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result) => { if (id === this.id && version === this.embedVersion) this.acceptEmbed(result, true); },
      error: (error) => { if (id === this.id && version === this.embedVersion) this.error.set(this.embedError(error, "Không thể tải thông tin nhúng.")); },
    });
  }
  private embedError(error: any, fallback: string) {
    return error?.error?.error?.code === "PUBLIC_BASE_URL_NOT_CONFIGURED"
      ? "Máy chủ chưa cấu hình RagHub Public URL. Hãy đặt PUBLIC_BASE_URL rồi khởi động lại API."
      : fallback;
  }
  async copy() {
    if (!this.code()) return;
    try {
      if (!navigator.clipboard) throw new Error();
      await navigator.clipboard.writeText(this.code());
      this.notice.set("Đã sao chép mã nhúng."); this.error.set("");
    } catch { this.error.set("Không thể sao chép tự động. Hãy chọn và copy toàn bộ mã nhúng bên dưới."); }
  }
}
