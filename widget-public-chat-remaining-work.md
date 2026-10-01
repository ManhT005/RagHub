# Việc còn lại — Widget nhúng → Public Chat được bảo vệ

> Cập nhật: 01/10/2026
>
> Cơ sở kiểm tra: nhánh `develop`, merge commit `39e56b9` sau PR #20.
>
> PR liên quan: #20 — `feat(widget): add embeddable chatbot`

## 1. Trạng thái hiện tại

Phần lõi của task đã có trên `develop`:

- [x] Web Component widget nhúng.
- [x] Script `/widget/raghub.js`.
- [x] Website demo cho widget.
- [x] API publish chatbot.
- [x] Embed key dạng `rgh_...`.
- [x] Database chỉ lưu hash của embed key.
- [x] Rotate embed key.
- [x] Chỉ chatbot đã publish mới được public chat.
- [x] Allowed Origins / Origin allowlist.
- [x] CORS chỉ echo origin đã được kiểm tra.
- [x] Public chat streaming bằng SSE.
- [x] Admin UI cấu hình origin, màu, title và greeting.
- [x] Database migration `20261001_0009_embed_widget`.
- [x] Backend tests cho key, origin, CORS và SSE frame.
- [x] CI của `develop` xanh sau merge PR #20: Backend, Frontend, Ingestion integration, Database migration, Docker Compose validation.

## 2. Việc bắt buộc còn lại

### 2.1. Rate limit public chat

- [x] Thêm rate limit cho endpoint:
  - `POST /api/v1/public/chatbots/{embed_key}/chat`
  - Có thể giới hạn theo embed key + IP/origin.
- [x] Xác định ngưỡng mặc định cho MVP, ví dụ:
  - requests / phút / IP
  - requests / phút / embed key
- [x] Trả lỗi ổn định khi vượt ngưỡng, ưu tiên HTTP `429`.
- [x] Có test backend cho:
  - request bình thường được xử lý;
  - vượt ngưỡng bị `429`;
  - rate limit không ảnh hưởng admin chat nội bộ.

**Acceptance criteria**

- Public endpoint không thể bị gọi không giới hạn chỉ bằng một embed key hợp lệ.
- Có test tự động bảo vệ behavior `429`.

### 2.2. Giới hạn concurrent public chat

- [x] Thêm giới hạn số phiên public chat đang chạy đồng thời.
- [x] Chọn cơ chế phù hợp với kiến trúc hiện tại (Redis semaphore/counter hoặc cơ chế tương đương).
- [x] Đảm bảo slot được giải phóng cả khi:
  - stream kết thúc;
  - client abort;
  - provider lỗi;
  - timeout.
- [x] Trả lỗi rõ ràng khi vượt giới hạn.

**Acceptance criteria**

- Một lượng lớn request đồng thời không thể tạo số stream không giới hạn.
- Có test cho acquire/release và failure path.

### 2.3. Đưa widget test vào CI

Hiện đã có test:

- `apps/chat-widget/tests/loader.test.cjs`

Nhưng workflow `.github/workflows/ci.yml` hiện chưa chạy test này.

Cần:

- [x] Thêm job hoặc step riêng cho `apps/chat-widget`.
- [x] Cài đúng Node version tương thích.
- [x] Chạy loader test trong CI.
- [x] Nếu có build artifact cho widget, thêm bước build/compile để kiểm tra TypeScript.

**Acceptance criteria**

- Push/PR thay đổi `apps/chat-widget/**` sẽ fail CI nếu widget test fail.
- CI hiển thị rõ kết quả widget test.

### 2.4. E2E / smoke test public widget

Unit test hiện mới kiểm tra behavior loader và backend helper/router. Cần kiểm tra luồng thật:

- [x] Publish chatbot thật trong test environment.
- [x] Nhận embed key.
- [x] Gọi `GET /config` từ origin được phép → thành công.
- [x] Gọi `GET /config` từ origin không được phép → `403`.
- [x] Gọi public chat từ origin hợp lệ → nhận SSE.
- [x] Gọi public chat từ origin không hợp lệ → `403`.
- [x] Rotate key → key cũ bị vô hiệu hóa.
- [x] Embed code không làm lộ key cũ sau rotate.
- [x] Widget demo tải được `/widget/raghub.js` qua Nginx.

**Acceptance criteria**

Có ít nhất một smoke test chạy được trên Docker Compose hoặc CI environment và xác minh end-to-end từ HTTP request đến SSE response.

## 3. Việc tài liệu cần sửa

### 3.1. README đang stale

README trên `develop` vẫn mô tả:

- Widget nhúng là “chưa có”.
- Allowed Origins/API key/rate limit là “chưa có”.

Trong khi widget, embed key và origin allowlist đã được triển khai.

Cần:

- [x] Cập nhật bảng “Chức năng”.
- [x] Cập nhật mục “Mục tiêu MVP còn lại”.
- [x] Thêm hướng dẫn publish chatbot và lấy embed code.
- [x] Thêm ví dụ script nhúng.
- [x] Mô tả rõ security model:
  - embed key;
  - allowed origins;
  - rotate key;
  - rate limit;
  - giới hạn concurrent chat.
- [x] Cập nhật trạng thái test/CI nếu smoke test được bổ sung.

## 4. Hardening nên làm trước khi production

Các mục dưới đây chưa nhất thiết chặn MVP, nhưng nên có trước khi public rộng:

- [x] Xem xét giới hạn độ dài / kích thước request public chat ở gateway.
- [x] Xem xét timeout riêng cho public stream.
- [x] Thêm logging có request ID, chatbot ID và mã lỗi nhưng không log embed key raw.
- [x] Thêm metrics cho số request public, `429`, `403`, số stream active và latency.
- [x] Xem xét chống abuse theo IP ngoài Origin allowlist.
- [x] Kiểm tra cache/proxy behavior của `/widget/raghub.js` và public SSE.
- [ ] Kiểm tra CSP/CORS trong môi trường domain thật (cần domain triển khai; đã thêm hướng dẫn kiểm tra).

## 5. Checklist nghiệm thu cuối task

- [ ] Publish chatbot từ Admin UI.
- [ ] Copy script nhúng và chạy trên website được allow.
- [ ] Widget hiển thị config đúng.
- [ ] Chat trả lời streaming và citation hoạt động.
- [x] Website ngoài allowlist không thể gọi public config/chat thành công.
- [x] Chatbot chưa publish không thể public chat.
- [x] Rotate key vô hiệu hóa key cũ.
- [x] Rate limit hoạt động và trả `429`.
- [x] Concurrent limit hoạt động.
- [x] Widget test đã được cấu hình trong CI; chưa chạy workflow remote trong phiên này.
- [x] E2E/smoke test chạy pass.
- [x] Database migration pass.
- [x] Docker Compose validation pass.
- [x] README và tài liệu tích hợp đã đồng bộ với implementation.

## 6. Thứ tự đề xuất thực hiện

1. Rate limit public chat.
2. Concurrent public chat limit.
3. Đưa widget test vào CI.
4. Thêm E2E/smoke test public flow.
5. Cập nhật README và tài liệu tích hợp.
6. Hardening production (logging, metrics, timeout, abuse protection).

## 7. Bằng chứng trước khi thực hiện kế hoạch

- Branch: `develop`
- Merge commit: `39e56b9`
- PR: `#20 feat(widget): add embeddable chatbot`
- CI run sau merge: thành công, 5/5 job.
- Backend test hiện có: `backend/tests/test_widget_public.py`
- Widget test hiện có: `apps/chat-widget/tests/loader.test.cjs`

## 8. Kết quả thực hiện ngày 01/10/2026

Triển khai trên nhánh hiện có `feature/embeddable-chat-widget`, commit riêng theo từng phần:

1. `8c38e9e` — rate limit Redis: 20 request/60 giây/IP, 120 request/60 giây/chatbot; HTTP 429, Retry-After và CORS cho origin đã xác thực; admin không bị ảnh hưởng.
2. `363e8a7` — concurrent lease: 4 stream/chatbot, 32 global, timeout public 90 giây; cleanup hoàn tất/lỗi/disconnect/timeout, lease hết hạn nếu worker chết.
3. `bed867f` — job Widget checks: Node 24.12.0, loader test, compile TypeScript 5.9.3.
4. `5153bef` — smoke HTTP qua Nginx, PostgreSQL và SSE; test atomic Lua với Redis thật; đưa cả hai vào CI integration.
5. `780e899` — README và `docs/widget-integration.md` đồng bộ.
6. Commit hardening kèm checklist này — body limit 16 KiB, trusted proxy/IP, timeout toàn response, đóng Redis/stream, redaction access logs, request ID và Redis metrics. Smoke bổ sung HTTP 429 thật và admin isolation.

Bằng chứng chạy cục bộ:

- Ruff: pass.
- Backend không cần hạ tầng: **157 passed**.
- Smoke widget và Redis thật: **2 passed**. Bao gồm publish, config, origin 403, OPTIONS, SSE conversation/citations/token/done, rotate key, code không chứa key cũ, unpublished 404, script/demo qua Nginx, body 413 và public 429/admin 200.
- Loader: **1 passed**; compile TypeScript cục bộ và Docker build: pass.
- Alembic upgrade trên database mới: pass; `alembic check`: no new upgrade operations.
- `nginx -t`, Compose config: pass.
- Metrics ghi nhận request/status/error/latency; slot global trở về 0 sau smoke.
- Chưa push hoặc chạy GitHub Actions remote; chỉ xác minh các lệnh tương ứng cục bộ và cấu hình workflow.

Môi trường test dùng project `raghub-widget-smoke`, volume riêng, HTTP 18080, PostgreSQL 15432, Redis 16379. Stack cục bộ cũ không khởi động được do database chứa revision `20260930_0010` không có trong nhánh này; không sửa/stamp/xóa database cũ để chạy test.

Các ô nghiệm thu browser ở mục 5 và CSP/domain thật ở mục 4 vẫn để trống: chưa có browser automation hoặc domain triển khai trong phiên. Smoke dùng workspace trống nên kiểm tra frame citations rỗng; chưa thay thế việc thử citation từ tài liệu/provider thật trong widget. Hướng dẫn nghiệm thu production nằm trong `docs/widget-integration.md`.
