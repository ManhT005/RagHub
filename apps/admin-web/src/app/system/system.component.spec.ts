import { provideHttpClient } from "@angular/common/http";
import { HttpTestingController, provideHttpClientTesting } from "@angular/common/http/testing";
import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { of } from "rxjs";

import { RaghubApiService } from "../core/raghub-api.service";
import { SystemComponent } from "./system.component";

describe("SystemComponent", () => {
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SystemComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: RaghubApiService,
          useValue: {
            organizations: () => of([{ id: "org-1", role: "ADMIN" }]),
          },
        },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it("uses ng-zorro cards and controls for system actions", () => {
    const fixture = TestBed.createComponent(SystemComponent);
    fixture.detectChanges();
    http.expectOne("/health/ready").flush({});

    fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll("nz-card")).toHaveLength(3);
    expect(fixture.nativeElement.querySelector("button[nz-button]")).not.toBeNull();
    expect(fixture.nativeElement.querySelector("a[nz-button]")).not.toBeNull();
  });
});
