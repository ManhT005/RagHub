import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnDestroy,
  Output,
  ViewChild,
  inject,
} from "@angular/core";
import { RaghubApiService } from "../core/raghub-api.service";

interface TurnstileApi {
  render(element: HTMLElement, options: Record<string, unknown>): string;
  reset(widgetId: string): void;
  remove(widgetId: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let scriptPromise: Promise<void> | null = null;

function loadTurnstile(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src =
      "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Turnstile script failed to load"));
    document.head.appendChild(script);
  });
  return scriptPromise;
}

@Component({
  selector: "raghub-turnstile",
  template: `<div #container class="turnstile-container"></div>`,
  styles: `
    :host { display: block; min-height: 65px; }
    .turnstile-container { display: flex; justify-content: center; }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TurnstileComponent implements AfterViewInit, OnDestroy {
  @Input({ required: true }) action = "";
  @Output() readonly tokenChange = new EventEmitter<string>();
  @Output() readonly availabilityChange = new EventEmitter<boolean>();
  @ViewChild("container", { static: true }) private container!: ElementRef<HTMLElement>;
  private readonly api = inject(RaghubApiService);
  private widgetId: string | null = null;

  ngAfterViewInit(): void {
    this.api.authSecurityConfig().subscribe({
      next: async (config) => {
        if (!config.turnstile_enabled) {
          this.availabilityChange.emit(false);
          return;
        }
        try {
          await loadTurnstile();
          this.widgetId = window.turnstile!.render(this.container.nativeElement, {
            sitekey: config.turnstile_site_key,
            action: this.action,
            appearance: "always",
            theme: "light",
            callback: (token: string) => this.tokenChange.emit(token),
            "expired-callback": () => this.tokenChange.emit(""),
            "error-callback": () => this.tokenChange.emit(""),
          });
          this.availabilityChange.emit(true);
        } catch {
          this.availabilityChange.emit(true);
          this.tokenChange.emit("");
        }
      },
      error: () => this.availabilityChange.emit(true),
    });
  }

  reset(): void {
    this.tokenChange.emit("");
    if (this.widgetId && window.turnstile) window.turnstile.reset(this.widgetId);
  }

  ngOnDestroy(): void {
    if (this.widgetId && window.turnstile) window.turnstile.remove(this.widgetId);
  }
}
