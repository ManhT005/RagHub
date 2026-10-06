# Tích hợp public widget

Trong Admin, chọn tổ chức, workspace và chatbot, mở màn hình Nhúng chatbot. Allowed origins phải là origin chính xác, ví dụ `https://www.example.com` hoặc `http://localhost:8081`. Publish để nhận key và mã script có URL tuyệt đối từ `PUBLIC_BASE_URL`; copy và dán trực tiếp. Key chỉ được trả tại lần publish đầu hoặc rotate; copy ngay lúc đó. Không dùng key này để truy cập API quản trị.

```html
<script src="https://raghub.example.com/widget/raghub.js"
        data-chatbot-key="rgh_REPLACE_WITH_YOUR_KEY" async></script>
```

Widget lấy config rồi POST chat qua `/api/v1/public/chatbots/{key}` trên origin của script RagHub. Config và chat đều yêu cầu chatbot đã publish và Origin được allow. Chat dùng SSE; preflight trả CORS cho origin đã kiểm tra. Khi rotate, config/chat với key cũ trả `404`. Sau reload, API trả `code: null`, `key: null`, `has_embed_key: true` cùng `script_src` và `public_base_url`; không có mã giả để copy. Cập nhật cấu hình vẫn giữ key cũ. Muốn nhận lại script hoàn chỉnh, tạo key mới rồi thay script trên website.

`PUBLIC_BASE_URL` là origin công khai của gateway RagHub, không lấy từ Host header của request. Local: `http://127.0.0.1:8080`. LAN: `http://192.168.1.50:8080` (đặt `LOCAL_BIND_ADDRESS=0.0.0.0` và mở cổng gateway). Production: `https://raghub.company.vn`. `localhost`/`127.0.0.1` trỏ tới máy của người mở browser, nên không dùng cho client ở máy khác. Chỉ nhận HTTP(S), không có path, credentials, query hoặc fragment. Production yêu cầu HTTPS; private self-host có thể chủ động đặt `PUBLIC_BASE_URL_ALLOW_HTTP=true`. Không cấu hình URL thì publish/rotate trả `503 PUBLIC_BASE_URL_NOT_CONFIGURED` trước khi đổi key.

Authenticated Admin/Workspace chat có quyền `chat.use` được preview cả Draft. Publication chỉ kiểm soát public widget/API. Lỗi runtime được hiển thị bằng thông báo an toàn và mã provider/search; không hiển thị raw upstream response.

Settings có live preview Desktop/Mobile chạy hoàn toàn tại browser; thay đổi theme không gọi public chat. Hex phải đúng 6 ký tự; origins được normalize và giới hạn 20. Nút Copy chỉ bật khi có script đầy đủ. Khi tạo key mới, UI yêu cầu xác nhận vì script cũ sẽ mất hiệu lực. Link demo dùng fragment `#key=...&api=...` để key không xuất hiện trong request/access log; trang demo xóa key khỏi URL khi tải widget. Demo vẫn yêu cầu origin của RagHub trong allowlist.

Key công khai và Origin có thể bị giả bởi client ngoài trình duyệt. Rate limit theo IP và chatbot cùng concurrent limit bảo vệ tài nguyên; chúng không xác thực danh tính khách truy cập. Không đưa tài liệu riêng tư vào chatbot public nếu người ngoài không được phép xem.

| Biến môi trường | Mặc định | Phạm vi |
| --- | --- | --- |
| `PUBLIC_CHAT_REQUESTS_PER_IP` | 20 | Request mỗi cửa sổ 60 giây/IP, trên mọi chatbot |
| `PUBLIC_CHAT_REQUESTS_PER_CHATBOT` | 120 | Request mỗi cửa sổ 60 giây/chatbot, giữ nguyên sau rotate |
| `PUBLIC_CHAT_CONCURRENT_PER_CHATBOT` | 4 | Stream đang chạy/chatbot |
| `PUBLIC_CHAT_CONCURRENT_GLOBAL` | 32 | Stream đang chạy/toàn bộ API worker |
| `PUBLIC_CHAT_STREAM_TIMEOUT_SECONDS` | 90 | Deadline public stream |
| `PUBLIC_CHAT_TRUSTED_PROXY_CIDRS` | Rỗng trong backend; `172.16.0.0/12` trong Compose | CIDR proxy được phép cung cấp `X-Real-IP`, phân cách bằng dấu phẩy |

Redis Lua thực hiện admission atomic. Cửa sổ rate bắt đầu từ request đầu tiên, không phải phút trên đồng hồ. Request đã được xác thực key/origin mới tính rate; admission concurrent bị từ chối vẫn tính rate. Quá giới hạn trả HTTP `429`, mã `PUBLIC_CHAT_RATE_LIMITED` hoặc `PUBLIC_CHAT_CONCURRENCY_LIMITED`, `Retry-After` và `error.details.retry_after_seconds`. Redis mất kết nối trả `503 PUBLIC_CHAT_UNAVAILABLE`; không mở giới hạn dự phòng. Admin chat dùng đường riêng.

Slot có token riêng, release khi response kết thúc, provider lỗi, timeout hoặc disconnect. Release lặp lại không ảnh hưởng slot khác. Lease hết hạn sau deadline + 10 giây nếu worker chết; Redis dùng thời gian server. Rate và slot dùng chatbot ID/IP hash, không lưu embed key raw.

Redis client/connection pool được tạo một lần trong ASGI lifespan của mỗi API worker, dùng chung cho admission, metrics và readiness; chỉ đóng khi application shutdown sau cleanup response. SSE chỉ giữ chatbot ID và lease token, không sở hữu connection hoặc đóng Redis khi kết thúc/bị từ chối. Release lỗi được ghi log và lease vẫn có hạn sử dụng để phục hồi khi Redis mất kết nối hoặc worker chết.

## Gateway và quan sát vận hành

Nginx giới hạn body public ở 16 KiB; schema giới hạn message ở 4.000 ký tự. SSE tắt buffering/cache; script dùng `no-store`. Timeout bao phủ cả thời gian gửi response tới client chậm. API được truy cập trực tiếp vẫn có giới hạn schema, nhưng production nên chỉ mở API qua gateway.

Nginx ghi đè `X-Real-IP` và `X-Forwarded-For`. Backend chỉ dùng `X-Real-IP` khi địa chỉ peer thuộc `PUBLIC_CHAT_TRUSTED_PROXY_CIDRS`; request trực tiếp không thể tự đặt IP để tránh rate limit. CIDR mẫu trong Compose phục vụ mạng Docker local; production phải đặt CIDR thực của proxy, tránh tin toàn bộ mạng dùng chung. Khi không cấu hình trust, request qua proxy chia sẻ hạn mức theo IP proxy.

Log public chứa request ID, chatbot ID nếu đã xác thực, status, mã lỗi và latency; không chứa URL/key/message/IP khách. Filter backend redacts `rgh_...`, kể cả access log Uvicorn. Nginx access log che key và bỏ query string; error log riêng của public route được tắt vì Nginx ghi nguyên URI trong lỗi upstream. Dùng log API có request ID để điều tra.

Redis hash `public:metrics` giữ tổng request, `status:403`, `status:429`, các `code:*` và `latency_ms_sum`. Latency là toàn bộ thời gian response, bao gồm stream; chia tổng cho số request để tính trung bình. Gauge stream active dùng `ZCOUNT public:active:global <unix-time-hiện-tại> +inf` (hoặc key `public:active:bot:<chatbot-id>`). Chỉ đếm lease chưa hết hạn. Metrics lỗi không chặn response; admission Redis lỗi vẫn trả `503`. Không công khai Redis hay endpoint metrics cho website.

Trước production, kiểm tra trên domain HTTPS thực: CSP cho phép `script-src` tới RagHub và `connect-src` tới API; allowlist khớp scheme/port; preflight, lỗi `429` và SSE đọc được trong browser; proxy/CDN giữ `no-store`, không buffer SSE và không log embed key. Domain thật không được giả định đã nghiệm thu bằng smoke local.

## Kiểm tra

```powershell
node --test apps/chat-widget/tests/loader.test.cjs
docker compose -f infrastructure/docker-compose.yml up -d --build --wait api nginx
cd backend
$env:RAGHUB_WIDGET_TEST_URL = 'http://localhost:8080'
$env:RAGHUB_TEST_DATABASE_URL = 'postgresql+asyncpg://raghub:raghub-local-only@localhost:5432/raghub'
$env:RAGHUB_TEST_REDIS_URL = 'redis://localhost:6379/15'
python -m pytest tests/test_widget_smoke.py tests/test_public_limits_integration.py
```

Chỉ chạy smoke với database test. Test tự tạo user đã xác minh để không gửi email, đăng nhập qua HTTP, tạo tổ chức/workspace/provider/chatbot rồi cleanup dữ liệu đã tạo. SSE đi qua Nginx với workspace trống nên trả câu trả lời không có ngữ cảnh và citations rỗng. Test cũng kiểm tra publish, preflight, origin bị chặn, rotate key, ngừng publish, cache script và demo. Test Redis sử dụng namespace ngẫu nhiên và cleanup riêng, kiểm tra burst request, global/per-chatbot slots, release lặp lại và lease hết hạn.

CI job Widget checks chạy loader và compile; job Ingestion integration chạy cả smoke widget và Redis trên Docker Compose. Kiểm tra Admin UI, browser thực, citation từ provider và CSP/domain production vẫn cần nghiệm thu theo môi trường triển khai.

## Nghiệm thu UI V2 có thể chạy lại

```powershell
cd apps/admin-web
npm run build
cd ../..
node apps/admin-web/node_modules/typescript/bin/tsc -p apps/chat-widget/tsconfig.json --outDir .backups/widget-ui-v2/widget
python scripts/check-widget-ui-browser.py
```

Script dùng Chromium headless (Playwright test tooling), bundle production và API giả lập; không tạo account hoặc gọi AI provider thực. Kiểm tra Settings ở 1440/375/320px, dark theme, swatch/hex, preview, show-once key, rotate có xác nhận và các nút ẩn/hiện mật khẩu. Widget được nhúng ở origin khác với CSP, CSS host cố tình gây xung đột, câu trả lời tiếng Việt dài và 5 nguồn mặc định đóng. Kiểm tra thêm mở/đóng nguồn, hội thoại mới, lỗi concurrency và origin. Host test dùng charset mặc định cũ để xác nhận script UTF-8 vẫn đọc đúng; Nginx và mã nhúng khai báo UTF-8 rõ ràng.

Screenshots và `report.json` lưu ở `.backups/widget-ui-v2/browser/`. Đây là kiểm tra render/interaction có thể lặp lại; smoke API qua gateway, provider thực và truy cập từ máy LAN khác vẫn phải chạy trên môi trường triển khai.
