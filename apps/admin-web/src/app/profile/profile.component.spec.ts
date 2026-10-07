import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { of } from "rxjs";

import { RaghubApiService } from "../core/raghub-api.service";
import { ProfileComponent } from "./profile.component";

describe("ProfileComponent", () => {
  it("shows the signed-in user email and verification state", async () => {
    await TestBed.configureTestingModule({
      imports: [ProfileComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            me: () =>
              of({
                id: "user-1",
                email: "owner@example.com",
                email_verified: true,
              }),
          },
        },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(ProfileComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain("owner@example.com");
    expect(fixture.nativeElement.querySelectorAll("nz-card")).toHaveLength(2);
    expect(fixture.nativeElement.querySelector("nz-avatar")).not.toBeNull();
    expect(fixture.nativeElement.querySelector("a[nz-button]")).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain("Email \u0111\u00e3 x\u00e1c th\u1ef1c");
  });
});
