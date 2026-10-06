import { DocumentMetadata } from "../core/api/document-api.service";
import { documentPollDelay, processingLabel, waitMessage } from "./document-progress";

describe("Embedding progress presentation", () => {
  const document = { status: "EMBEDDING", stage: "EMBEDDING", progress: 77,
    embedded_chunks: 34, total_chunks: 49, work_state: "WAITING_QUOTA",
    waiting_reason: "PROVIDER_RATE_LIMIT" } as DocumentMetadata;
  it("explains rate limits without changing the stage or progress", () => {
    expect(processingLabel(document)).toBe("Đang chờ API");
    expect(waitMessage({ ...document, retry_at: "2026-10-06T16:00:08Z" }, Date.parse("2026-10-06T16:00:00Z"))).toContain("8 giây");
    expect(document.progress).toBe(77);
    expect(document.embedded_chunks).toBe(34);
  });
  it("backs off waits, honors near retry times, and stops terminal documents", () => {
    expect(documentPollDelay([document])).toBe(10000);
    expect(documentPollDelay([{ ...document, retry_at: "2026-10-06T16:00:03Z" }], Date.parse("2026-10-06T16:00:00Z"))).toBe(3000);
    expect(documentPollDelay([{ ...document, work_state: "RUNNING", waiting_reason: null }])).toBe(3000);
    expect(documentPollDelay([{ ...document, status: "READY" }])).toBeNull();
    expect(documentPollDelay([{ ...document, status: "FAILED" }])).toBeNull();
  });
  it("keeps fast polling if another document is running", () => {
    expect(documentPollDelay([document, { ...document, work_state: "RUNNING" }])).toBe(3000);
    expect(processingLabel({ ...document, waiting_reason: "WAITING_FOR_WORKER" })).toBe("Đang chờ worker");
  });
});
