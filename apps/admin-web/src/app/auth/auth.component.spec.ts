import { ComponentFixture, TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { of } from "rxjs";

import { AuthComponent } from "./auth.component";
import { provideHttpClient } from "@angular/common/http";
import { RaghubApiService } from "../core/raghub-api.service";

describe("AuthComponent", () => {
  let fixture: ComponentFixture<AuthComponent>;
  let component: AuthComponent;
  let api: {
    login: ReturnType<typeof vi.fn>;
    forgotPassword: ReturnType<typeof vi.fn>;
    authSecurityConfig: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    api = {
      login: vi.fn(() => of({ access_token: "login-token" })),
      forgotPassword: vi.fn(() => of({ message: "sent" })),
      authSecurityConfig: vi.fn(() =>
        of({ turnstile_enabled: false, turnstile_site_key: "" }),
      ),
    };
    await TestBed.configureTestingModule({
      imports: [AuthComponent],
      providers: [
        provideHttpClient(),
        provideRouter([]),
        { provide: RaghubApiService, useValue: api },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(AuthComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it("shows only internal login and password recovery options", () => {
    const text = fixture.nativeElement.textContent;

    expect(text).not.toContain("Đăng ký");
    expect(fixture.nativeElement.querySelector("#google-signin")).toBeNull();
    expect(text).toContain("Quên mật khẩu");
  });
});
