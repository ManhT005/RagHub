# Báo cáo WS1 - RAG Reliability Hardening

Ngày: 2026-10-05
Workstream: WS1 - Release gate + telemetry + baseline
Trạng thái: Đã triển khai code đo lường/gate; chưa chụp baseline live vì cần backend live, token hợp lệ và `GEMINI_API_KEY`.

## Tóm tắt luồng hiện tại sau khi scout

- Retrieval nhận `RetrievalScope`, query và limit từ `RetrieveContextUseCase`.
- Query được normalize rồi gọi provider embedding để tạo vector truy vấn.
- Elasticsearch chạy BM25 và vector kNN song song trong `ChunkSearch`.
- Hai nhánh được hợp nhất bằng RRF, sau đó áp diversity cap theo document.
- `RetrieveContextUseCase` có thể chạy reranker nếu flag bật, nhưng đợt này giữ nguyên không bật/thêm model.
- Relevance gate hiện mở rộng trên hook có sẵn, vẫn mặc định tắt nếu flag/config không bật.
- Sau gate, readiness filter loại các document/chunk chưa sẵn sàng.
- Nếu không còn hit, RAG trả empty-context fallback và không tạo citation giả.
- Chat path tạo context bundle, resolve citation inventory, build prompt và stream provider response.
- Citation validator hiện observe-only, ghi invalid/coverage qua telemetry nếu có telemetry/citation observer.
- Pending clarification hiện vẫn còn fallback dựa vào text prefix trong `stream_chat.py`; phần này thuộc WS4, chưa sửa ở WS1.
- Điểm mâu thuẫn với brief: production eval đã có script, nhưng trước WS1 chưa có release gate threshold/fail-code và chưa tách provider error khỏi metric chất lượng chat.

## File đã sửa/tạo

- `backend/app/infrastructure/elasticsearch/chunks.py`
- `backend/app/composition/retrieval.py`
- `raghub-core/src/raghub_core/application/retrieval/retrieve_context.py`
- `backend/scripts/run_production_eval.py`
- `backend/tests/test_rag_release_gate.py`
- `backend/tests/test_telemetry_gc.py`
- `plans/reports/261005-rag-reliability-hardening-ws1.md`

## Thay đổi và lý do

- Thêm telemetry chi tiết trong retrieval:
  - `retrieval_es_bm25`
  - `retrieval_es_vector`
  - `retrieval_rrf_diversity`
  - `retrieval_es_total`
  - `readiness_filter`
  - `relevance_gate`
  - counters: BM25/vector/fused/ready hits.
- Dùng chung `LoggingTelemetry` cho `RetrieveContextUseCase` và `ChunkSearch` để log correlation nhất quán.
- Nâng `run_production_eval.py` thành release gate có `--gate`, threshold CLI và exit code `2` nếu fail.
- Thêm retry/backoff có giới hạn cho SSE chat eval qua `--chat-retries` và `--retry-backoff-seconds`.
- Tách provider/rate-limit error khỏi chat quality metrics, tránh tính nhầm lỗi quota thành lỗi citation/fact recall.
- Artifact eval mới có `release_gate`, `provider_error_policy`, `provider_error`, `chat_attempts` theo từng case.

## Số liệu trước/sau

- Trước WS1: script live eval có summary nhưng chưa có release gate/fail-code, provider error còn lẫn vào metric chat quality.
- Sau WS1: script có gate deterministic, threshold mặc định:
  - `rejection_f1 >= 0.90`
  - `citation_precision >= 1.00`
  - `answerable_direct_pass_rate >= 0.90`
  - `citation_coverage_mean >= 0.85`
  - `facts_recall >= 0.85`
  - `provider_errors <= 0`
- Baseline live chưa chạy trong lượt này vì thiếu điều kiện runtime live/token/provider key trong sandbox. Không kết luận đạt KPI.

## Test đã chạy

- `backend\.venv\Scripts\python.exe -m py_compile backend\app\infrastructure\elasticsearch\chunks.py backend\app\composition\retrieval.py raghub-core\src\raghub_core\application\retrieval\retrieve_context.py backend\scripts\run_production_eval.py backend\tests\test_rag_release_gate.py`
  - Kết quả: PASS.
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_rag_release_gate.py backend\tests\test_telemetry_gc.py -q`
  - Kết quả: `10 passed, 6 skipped`.
  - Lưu ý: các async test cũ trong `test_telemetry_gc.py` vẫn bị skip do pytest async plugin/config chưa hoạt động trong environment hiện tại; test mới dùng `asyncio.run()` để đảm bảo phần WS1 thật sự chạy.
- `backend\.venv\Scripts\python.exe backend\scripts\run_production_eval.py --help`
  - Kết quả: PASS, CLI hiển thị các option gate mới.

## Acceptance WS1

- [x] Telemetry tách được các đoạn chính: embedding, BM25, vector, RRF/diversity, readiness, relevance gate, rerank nếu bật.
- [x] Script gate có thể chạy bằng một lệnh và fail bằng exit code khi metric không đạt.
- [x] Provider/rate-limit error được phân loại riêng, không tính nhầm vào citation/fact quality metrics.
- [ ] Baseline live JSON/CSV ghi commit + config: chưa chạy được trong sandbox vì cần backend live + token/Gemini key.
- [ ] p50/p95 theo từng đoạn từ log production: code đã emit, cần chạy live để thu log thật.

## Rủi ro và tồn đọng

- Chưa thể tuyên bố đạt release KPI vì thiếu baseline live và 3 run ổn định cùng commit/config.
- `run_production_eval.py` hiện đo latency tổng retrieval/chat trong artifact; latency chi tiết từng đoạn đi qua structured telemetry log. Nếu muốn artifact tự gom p50/p95 theo stage, cần thêm collector/log sink ở WS1.1 hoặc dùng backend log aggregator.
- `followup_resolution_rate`, `unnecessary_clarification_rate` đã có ở benchmark clarification offline trước đó, nhưng chưa được tích hợp vào live gate script này.
- No-answer gate vẫn yếu về logic chất lượng; WS2 mới xử lý rejection features, WS1 chỉ dựng bằng chứng và fail gate.

## Đề xuất ngưỡng tạm cho WS2/WS5

- Citation coverage/fact recall: bắt đầu với `>= 0.85` trên golden live, sau baseline thật có thể nâng lên `>= 0.90` nếu variance thấp.
- Retrieval latency p95: chốt sau baseline live; tạm đề xuất không tăng quá `+15%` so với baseline WS1 và có cap tuyệt đối do người vận hành chọn theo môi trường deploy.

## Lệnh chạy baseline live đề xuất

```powershell
cd C:\Users\khact\Desktop\RagHub\backend
.\.venv\Scripts\python.exe scripts\run_production_eval.py `
  --out ..\artifacts\rag_production_eval_ws1_baseline.json `
  --mint-email <email-admin> `
  --gate `
  --chat-retries 2 `
  --retry-backoff-seconds 2
```