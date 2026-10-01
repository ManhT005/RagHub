import { ChangeDetectionStrategy, Component } from "@angular/core";
import { RouterLink, RouterLinkActive } from "@angular/router";
import { NzButtonModule } from "ng-zorro-antd/button";

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
        routerLink="/lien-he"
        routerLinkActive="active"
        ariaCurrentWhenActive="page"
        >Liên hệ</a
      >
    </div>
    <a nz-button nzType="primary" routerLink="/auth">Đăng nhập</a>
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
      gap: 28px;
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
export class PublicNavComponent {}
