import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { of } from "rxjs";

import { ProviderApiService } from "../../core/api/provider-api.service";
import { RaghubApiService } from "../../core/raghub-api.service";
import { AiProvidersComponent } from "./ai-providers.component";

describe("AiProvidersComponent", () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AiProvidersComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            organizations: () =>
              of([{ id: "org-1", name: "RagHub", slug: "raghub", role: "ADMIN" }]),
          },
        },
        {
          provide: ProviderApiService,
          useValue: {
            connections: () =>
              of([
                {
                  id: "provider-1",
                  catalog_id: "google-gemini",
                  provider_type: "GOOGLE_GEMINI",
                  name: "Google Gemini",
                  base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
                  status: "CONNECTED",
                  enabled: true,
                  model_count: 2,
                  last_latency_ms: 1126,
                },
              ]),
            catalog: () => of([]),
          },
        },
      ],
    }).compileComponents();
  });

  it("separates module navigation from provider filters using ng-zorro controls", () => {
    const fixture = TestBed.createComponent(AiProvidersComponent);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const navigation = element.querySelector(".ai-module-tabs");
    const filters = element.querySelector(".provider-filters");

    expect(navigation?.querySelectorAll("a[nz-button]").length).toBe(3);
    expect(navigation?.querySelector('a[href="/system/ai/models"]')).not.toBeNull();
    expect(navigation?.querySelector('a[href="/system/ai/local"]')).not.toBeNull();
    expect(filters?.querySelector("input[nz-input]")).not.toBeNull();
    expect(filters?.querySelector("nz-select")).not.toBeNull();
    expect(filters?.querySelector("a")).toBeNull();
    expect(element.querySelector("nz-card.provider-card")).not.toBeNull();
  });
});
