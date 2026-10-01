# Tích hợp public widget

Trong Admin, chọn tổ chức, workspace và chatbot, mở màn hình Nhúng chatbot. Allowed origins phải là origin chính xác, ví dụ `https://www.example.com` hoặc `http://localhost:8081`. Publish để nhận key và mã script; thay đường dẫn script bằng URL tuyệt đối của RagHub. Key chỉ được trả tại lần publish đầu hoặc rotate; copy ngay lúc đó. Không dùng key này để truy cập API quản trị.

```html
<script src="https://raghub.example.com/widget/raghub.js"
        data-chatbot-key="rgh_REPLACE_WITH_YOUR_KEY" async></script>
```

Widget lấy config rồi POST chat qua `/api/v1/public/chatbots/{key}`. Config và chat đều yêu cầu chatbot đã publish và Origin được allow. Chat dùng SSE; preflight trả CORS cho origin đã kiểm tra. Khi rotate, config/chat với key cũ trả `404`; mã nhúng lấy lại qua API chứa `REDACTED`. Khi chỉnh cấu hình widget đã publish, dùng lại key đã giữ hoặc rotate để nhận key mới.

Key công khai và Origin có thể bị giả bởi client ngoài trình duyệt. Rate limit theo IP và chatbot cùng concurrent limit bảo vệ tài nguyên; chúng không xác thực danh tính khách truy cập. Không đưa tài liệu riêng tư vào chatbot public nếu người ngoài không được phép xem.

| Biến môi trường | Mặc định | Phạm vi |
| --- | --- | --- |
| `PUBLIC_CHAT_REQUESTS_PER_IP` | 20 | Request mỗi cửa sổ 60 giây/IP, trên mọi chatbot |
| `PUBLIC_CHAT_REQUESTS_PER_CHATBOT` | 120 | Request mỗi cửa sổ 60 giây/chatbot, giữ nguyên sau rotate |
| `PUBLIC_CHAT_CONCURRENT_PER_CHATBOT` | 4 | Stream đang chạy/chatbot |
| `PUBLIC_CHAT_CONCURRENT_GLOBAL` | 32 | Stream đang chạy/toàn bộ API worker |
| `PUBLIC_CHAT_STREAM_TIMEOUT_SECONDS` | 90 | Deadline public stream |

Redis Lua thực hiện admission atomic. Cửa sổ rate bắt đầu từ request đầu tiên, không phải phút trên đồng hồ. Request đã được xác thực key/origin mới tính rate; admission concurrent bị từ chối vẫn tính rate. Quá giới hạn trả HTTP `429`, mã `PUBLIC_CHAT_RATE_LIMITED` hoặc `PUBLIC_CHAT_CONCURRENCY_LIMITED`, `Retry-After` và `error.details.retry_after_seconds`. Redis mất kết nối trả `503 PUBLIC_CHAT_UNAVAILABLE`; không mở giới hạn dự phòng. Admin chat dùng đường riêng.

Slot có token riêng, release khi response kết thúc, provider lỗi, timeout hoặc disconnect. Release lặp lại không ảnh hưởng slot khác. Lease hết hạn sau deadline + 10 giây nếu worker chết; Redis dùng thời gian server. Rate và slot dùng chatbot ID/IP hash, không lưu embed key raw.

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
