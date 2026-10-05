import { chatError } from "./chat-error";

describe("chat diagnostics", () => {
  it("preserves provider error codes with actionable messages", () => {
    expect(chatError({ code: "PROVIDER_AUTH_FAILED", message: "upstream-secret" })).toContain("API key");
    expect(chatError({ code: "PROVIDER_AUTH_FAILED" })).toContain("Mã lỗi: PROVIDER_AUTH_FAILED");
    expect(chatError({ code: "SEARCH_UNAVAILABLE" })).toContain("Vector search");
  });
  it("does not display raw upstream messages or malformed codes", () => {
    expect(chatError({ code: "OTHER", message: "upstream-secret" })).not.toContain("upstream-secret");
    expect(chatError({ code: "<script>secret</script>" })).not.toContain("secret");
  });
});
