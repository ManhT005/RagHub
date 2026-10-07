import { ChangeDetectionStrategy, Component, inject } from "@angular/core";
import { RouterLink, RouterLinkActive } from "@angular/router";
import { NzButtonModule } from "ng-zorro-antd/button";
import { ThemeService } from "../core/theme.service";

@Component({
  selector: "raghub-public-nav",
  imports: [RouterLink, RouterLinkActive, NzButtonModule],
  template: ` <nav aria-label="Điều hướng RAGHub">
    <a class="brand" routerLink="/"
      ><img src="assets/logo.png" alt="" />RAGHub</a
    >
    <div class="nav-links">
      <a
        routerLink="/"
        routerLinkActive="active"
        [routerLinkActiveOptions]="{ exact: true }"
        ariaCurrentWhenActive="page"
        >Trang chủ</a
      >
      <a
        routerLink="/tinh-nang"
        routerLinkActive="active"
        ariaCurrentWhenActive="page"
        >Tính năng</a
      >
      <a
        routerLink="/giai-phap"
        routerLinkActive="active"
        ariaCurrentWhenActive="page"
        >Giải pháp</a
      >
      <a
        routerLink="/huong-dan"
        routerLinkActive="active"
        ariaCurrentWhenActive="page"
        >Hướng dẫn</a
      >
      <a
        routerLink="/lien-he"
        routerLinkActive="active"
        ariaCurrentWhenActive="page"
        >Liên hệ</a
      >
    </div>
    <div class="nav-actions">
      <button
        type="button"
        class="theme-toggle"
        [attr.aria-label]="darkMode() ? 'Chuyển sang nền sáng' : 'Chuyển sang nền tối'"
        [attr.aria-pressed]="darkMode()"
        (click)="toggleTheme()"
      >
        @if (darkMode()) {
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="4" />
            <path
              d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.65 17.65l1.42 1.42M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.65 6.35l1.42-1.42"
            />
          </svg>
        } @else {
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5 8.5 8.5 0 1 0 20.5 14.2Z" />
          </svg>
        }
      </button>
      <a nz-button nzType="primary" routerLink="/auth">Đăng nhập</a>
    </div>
  </nav>`,
  styles: `
    :host {
      position: sticky;
      top: 12px;
      z-index: 100;
      display: block;
      padding-top: 16px;
    }
    nav {
      min-height: 62px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      padding: 0 18px;
      border: 1px solid #d8e7f8;
      border-radius: 10px;
      background: #ffffffd9;
      box-shadow: 0 6px 18px #1b5da10d;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      color: #0a2050;
      font-size: 20px;
      font-weight: 750;
    }
    .brand img {
      width: 28px;
      height: 28px;
      object-fit: contain;
    }
    .nav-links {
      display: flex;
      gap: 24px;
      margin-left: auto;
      margin-right: 6%;
    }
    .nav-links a {
      display: flex;
      align-items: center;
      min-height: 44px;
      font-size: 14px;
      color: #173665;
      padding: 0 2px;
      border-bottom: 2px solid transparent;
      transition:
        color 0.18s ease,
        border-color 0.18s ease;
    }
    .nav-links a:hover,
    .nav-links a.active {
      color: #0866ff;
      border-bottom-color: #0866ff;
    }
    .nav-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .theme-toggle {
      width: 40px;
      height: 40px;
      padding: 0;
      display: grid;
      place-items: center;
      color: #274b78;
      background: #fff;
      border: 1px solid #dce8f6;
      border-radius: 12px;
      cursor: pointer;
      transition:
        background 180ms ease,
        border-color 180ms ease,
        color 180ms ease;
    }
    .theme-toggle:hover,
    .theme-toggle[aria-pressed="true"] {
      color: #0866ff;
      background: #edf5ff;
      border-color: #c8dcf4;
    }
    .theme-toggle svg {
      width: 20px;
      height: 20px;
      fill: none;
      stroke: currentColor;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke-width: 1.8;
    }
    .theme-toggle:focus-visible {
      outline: 2px solid #0866ff;
      outline-offset: 2px;
    }
    :host-context(html[data-theme="dark"]) nav {
      background: rgba(17, 31, 50, 0.96);
      border-color: #2a405b;
      box-shadow: 0 6px 18px rgba(0, 0, 0, 0.3);
    }
    :host-context(html[data-theme="dark"]) .brand {
      color: #edf5ff;
    }
    :host-context(html[data-theme="dark"]) .nav-links a {
      color: #a9bdd5;
    }
    :host-context(html[data-theme="dark"]) .nav-links a:hover,
    :host-context(html[data-theme="dark"]) .nav-links a.active {
      color: #85b8ff;
      border-bottom-color: #85b8ff;
    }
    :host-context(html[data-theme="dark"]) .theme-toggle {
      color: #e5eef9;
      background: #111f32;
      border-color: #2a405b;
    }
    :host-context(html[data-theme="dark"]) .theme-toggle:hover,
    :host-context(html[data-theme="dark"]) .theme-toggle[aria-pressed="true"] {
      background: #18304d;
      color: #85b8ff;
    }
    a:focus-visible {
      outline: 2px solid #0866ff;
      outline-offset: 4px;
    }
    @media (max-width: 900px) {
      .nav-links {
        gap: 18px;
        margin-right: 0;
      }
    }
    @media (max-width: 640px) {
      :host {
        top: 8px;
        padding-top: 8px;
      }
      nav {
        flex-wrap: wrap;
        gap: 8px;
        padding: 10px 14px;
      }
      .brand {
        font-size: 18px;
      }
      .nav-links {
        order: 3;
        width: 100%;
        justify-content: space-between;
        gap: 8px;
      }
      .nav-links a {
        font-size: 12px;
        min-height: 40px;
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PublicNavComponent {
  private readonly theme = inject(ThemeService);
  protected readonly darkMode = this.theme.darkMode;

  protected toggleTheme(): void {
    this.theme.toggleTheme();
  }
}
