import { AfterViewInit, Directive, ElementRef, OnDestroy, Renderer2, inject } from "@angular/core";

/** Adds a native, keyboard-accessible visibility button without replacing the form input. */
@Directive({ selector: 'input[type="password"]' })
export class PasswordToggleDirective implements AfterViewInit, OnDestroy {
  private readonly input = inject<ElementRef<HTMLInputElement>>(ElementRef).nativeElement;
  private readonly renderer = inject(Renderer2);
  private wrapper?: HTMLSpanElement;
  private button?: HTMLButtonElement;
  private unlisten?: () => void;
  private observer?: MutationObserver;
  private visible = false;

  ngAfterViewInit() {
    const parent = this.input.parentNode;
    if (!parent) return;
    this.wrapper = this.renderer.createElement("span");
    this.renderer.addClass(this.wrapper, "rh-password-control");
    this.renderer.insertBefore(parent, this.wrapper, this.input);
    this.renderer.appendChild(this.wrapper, this.input);
    this.button = this.renderer.createElement("button");
    this.renderer.setAttribute(this.button, "type", "button");
    this.renderer.addClass(this.button, "rh-password-toggle");
    if (!this.input.id) this.renderer.setAttribute(this.input, "id", `rh-password-${crypto.randomUUID()}`);
    this.renderer.setAttribute(this.button, "aria-controls", this.input.id);
    this.renderer.appendChild(this.wrapper, this.button);
    this.unlisten = this.renderer.listen(this.button, "click", () => {
      this.visible = !this.visible;
      this.renderer.setProperty(this.input, "type", this.visible ? "text" : "password");
      this.update();
    });
    this.observer = new MutationObserver(() => this.update());
    this.observer.observe(this.input, { attributes: true, attributeFilter: ["disabled"] });
    this.update();
  }
  private update() {
    if (!this.button) return;
    const label = this.input.autocomplete === "off" ? "nội dung" : "mật khẩu";
    const action = `${this.visible ? "Ẩn" : "Hiện"} ${label}`;
    this.renderer.setAttribute(this.button, "aria-label", action);
    this.renderer.setAttribute(this.button, "title", action);
    this.renderer.setAttribute(this.button, "aria-pressed", String(this.visible));
    this.renderer.setProperty(this.button, "disabled", this.input.disabled);
    this.renderer.setProperty(this.button, "innerHTML", `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>${this.visible ? '<path d="m3 3 18 18"/>' : ""}</svg>`);
  }
  ngOnDestroy() {
    this.unlisten?.();
    this.observer?.disconnect();
    const parent = this.wrapper?.parentNode;
    if (parent && this.wrapper) {
      this.renderer.insertBefore(parent, this.input, this.wrapper);
      this.renderer.removeChild(parent, this.wrapper);
    }
  }
}
