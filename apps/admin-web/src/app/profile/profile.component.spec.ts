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
    expect(fixture.nativeElement.textContent).toContain("Email đã xác thực");
  });
});
