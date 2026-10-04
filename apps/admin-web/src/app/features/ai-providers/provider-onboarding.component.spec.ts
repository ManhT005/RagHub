import { TestBed } from "@angular/core/testing";
import { provideNoopAnimations } from "@angular/platform-browser/animations";
import { of, throwError } from "rxjs";
import { ProviderOnboardingComponent } from "./provider-onboarding.component";
import {
  ProviderApiService,
  ProviderCatalogItem,
  selectableModel,
} from "../../core/api/provider-api.service";
import { apiError } from "../../core/api/api-error";

describe("Provider onboarding", () => {
  const catalog: ProviderCatalogItem[] = [
    {
      id: "ollama",
      name: "Ollama",
      category: "Local",
      provider_type: "OLLAMA",
      default_base_url: "http://ollama:11434",
      capabilities: ["CHAT"],
      supports_model_discovery: true,
      auth_type: "NONE",
      docs_url: null,
      api_key_url: null,
      status: "SUPPORTED",
    },
  ];
  const api = {
    create: vi.fn(),
    update: vi.fn(),
    test: vi.fn(),
    discover: vi.fn(),
    register: vi.fn(),
  };
  beforeEach(async () => {
    vi.clearAllMocks();
    api.create.mockReturnValue(of({ id: "connection-1" }));
    api.test.mockReturnValue(
      of({ status: "CONNECTED", latency_ms: 8, error_code: null }),
    );
    api.discover.mockReturnValue(
      of([{ model: "local-model", capabilities: ["CHAT"], dimension: null }]),
    );
    api.register.mockReturnValue(of({ model: "local-model" }));
    await TestBed.configureTestingModule({
      imports: [ProviderOnboardingComponent],
      providers: [
        provideNoopAnimations(),
        { provide: ProviderApiService, useValue: api },
      ],
    }).compileComponents();
  });
  function fixture() {
    const fixture = TestBed.createComponent(ProviderOnboardingComponent);
    fixture.componentRef.setInput("organizationId", "org-1");
    fixture.componentRef.setInput("catalog", catalog);
    fixture.componentRef.setInput("visible", true);
    fixture.detectChanges();
    return fixture;
  }
  it("tests a real connection before entering model selection and survives catalog refresh", () => {
    const view = fixture();
    const component = view.componentInstance;
    component["choose"](catalog[0]);
    component["test"]();
    expect(api.create).toHaveBeenCalledWith("org-1", {
      name: "Ollama",
      provider_type: "OLLAMA",
      base_url: "http://ollama:11434",
      catalog_id: 'ollama',
    });
    expect(component["step"]()).toBe(2);
    view.componentRef.setInput("catalog", [...catalog]);
    view.detectChanges();
    expect(component["step"]()).toBe(2);
    expect(component["choices"]()[0].model).toBe("local-model");
    view.destroy();
  });
  it("never progresses past a failed authentication check", () => {
    api.test.mockReturnValue(
      of({ status: "ERROR", error_code: "PROVIDER_AUTH_FAILED" }),
    );
    const view = fixture();
    const component = view.componentInstance;
    component["choose"](catalog[0]);
    component["test"]();
    expect(component["step"]()).toBe(1);
    expect(api.discover).not.toHaveBeenCalled();
    expect(component["error"]()).toContain("API key");
    view.destroy();
  });

  it('preserves custom brand identity when two catalog entries share a runtime adapter', () => {
    const view = fixture();
    const brands = ['openai', 'compatible'].map(id => ({ ...catalog[0], id, name: id, provider_type: 'OPENAI_COMPATIBLE' as const }));
    view.componentRef.setInput('catalog', brands);
    view.componentRef.setInput('connection', { id: 'custom', name: 'Private API', catalog_id: 'compatible', provider_type: 'OPENAI_COMPATIBLE', base_url: 'https://api.openai.com/v1' });
    view.detectChanges();
    expect(view.componentInstance['selected']()?.id).toBe('compatible');
    view.destroy();
  });

  it('resolves legacy custom connections by base URL, independently of their name', () => {
    const view = fixture();
    view.componentRef.setInput('catalog', ['openai', 'compatible'].map(id => ({ ...catalog[0], id, provider_type: 'OPENAI_COMPATIBLE' })));
    view.componentRef.setInput('connection', { id: 'legacy', name: 'OpenAI', catalog_id: null, provider_type: 'OPENAI_COMPATIBLE', base_url: 'https://custom.example/v1' });
    view.detectChanges();
    expect(view.componentInstance['selected']()?.id).toBe('compatible');
    view.destroy();
  });
  it("allows manual IDs when discovery is unsupported and validates registration through backend", () => {
    api.test.mockReturnValue(
      of({ status: "UNTESTED", error_code: "MODEL_DISCOVERY_UNSUPPORTED" }),
    );
    const view = fixture();
    const component = view.componentInstance;
    component["choose"](catalog[0]);
    component["test"]();
    expect(component["step"]()).toBe(2);
    component["manualId"] = "local-model";
    component["addManual"]();
    component["save"]();
    expect(api.register).toHaveBeenCalledWith("connection-1", {
      model: "local-model",
      display_name: "local-model",
      capability: "CHAT",
    });
    view.destroy();
  });
  it("uses safe localized errors and releases the busy state after failed requests", () => {
    api.create.mockReturnValue(
      throwError(() => ({
        error: {
          error: { code: "PROVIDER_UNREACHABLE", message: "raw-secret" },
        },
      })),
    );
    const view = fixture();
    const component = view.componentInstance;
    component["choose"](catalog[0]);
    component["test"]();
    expect(component["busy"]()).toBe(false);
    expect(component["error"]()).not.toContain("raw-secret");
    view.destroy();
  });
  it("requires model and connection health for selection", () => {
    const model = {
      enabled: true,
      connection_enabled: true,
      connection_status: "CONNECTED",
      availability_status: "AVAILABLE",
    } as Parameters<typeof selectableModel>[0];
    expect(selectableModel(model)).toBe(true);
    expect(selectableModel({ ...model, connection_status: "DEGRADED" })).toBe(
      false,
    );
    expect(
      apiError({ error: { error: { code: "UNKNOWN", message: "raw-stack" } } }),
    ).not.toContain("raw-stack");
  });
  it("closes the drawer after every selected model finishes registration", () => {
    const view = fixture(),
      component = view.componentInstance;
    const closed = vi.fn();
    component.closed.subscribe(closed);
    component["choose"](catalog[0]);
    component["test"]();
    component["manualId"] = "manual-model";
    component["addManual"]();
    api.register.mockReturnValue(of({ model: "manual-model" }));
    component["save"]();
    expect(closed).toHaveBeenCalledTimes(1);
    expect(component["busy"]()).toBe(false);
    view.destroy();
  });
});
