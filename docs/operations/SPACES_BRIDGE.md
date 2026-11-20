# Hugging Face Spaces / ZeroGPU bridge

Bridge tùy chọn cho Space Gradio có queue API hiện đại. Không phải Hugging Face
Inference Router; không dùng endpoint `router.huggingface.co`. Không cần migration
database và không thay đổi embedding/index đang có.

## Chạy

Dùng environment backend đã cài dependencies. Đặt các biến môi trường riêng:

- `SPACE_URL`: origin Space, ví dụ `https://owner-space.hf.space`.
- `SPACE_API_NAME`: tên API trong trang **Use via API**, mặc định `predict`.
- `SPACE_INPUT_TEMPLATE`: JSON array đúng thứ tự input endpoint, ví dụ
  `["$prompt", [], 512, 0.7]`. Chỉ giá trị nguyên chuỗi `$prompt` được thay bằng
  prompt hội thoại; các tham số khác giữ nguyên. Không dùng ví dụ này nếu Space
  có signature khác.
- `SPACE_OUTPUT_INDEX`: vị trí output chứa chuỗi câu trả lời, mặc định `0`.
- `HF_TOKEN`: token Hugging Face, chỉ ở phía server; quota tính cho tài khoản này.
- `SPACES_BRIDGE_KEY`: khóa ngẫu nhiên riêng để bảo vệ bridge, bắt buộc.
- `SPACE_MODEL`: ID model bridge quảng bá, mặc định `space-chat`.

Từ `backend/`:

```sh
uvicorn app.spaces_bridge:app --host 127.0.0.1 --port 8091
```

Publish bằng HTTPS reverse proxy có xác thực Bearer như trên. Trong RagHub chọn
provider OpenAI-compatible, Base URL `https://YOUR-BRIDGE/v1`, API key bằng
`SPACES_BRIDGE_KEY`, đăng ký `SPACE_MODEL` với capability CHAT.
Không dùng localhost của VPS làm URL từ container API: đó là localhost container.

## Giới hạn

- Phải chọn Space và xem API signature trước. Chỉ hỗ trợ output chuỗi và input
  text; chưa hỗ trợ output chat-history, file, ảnh hoặc tool calls.
- Lịch sử/system prompt được ghép thành text, không đảm bảo phân tách role như
  API chat native. Chọn Space có prompt phù hợp cho RAG.
- Streaming trả kết quả một lần khi Space hoàn tất, không stream token thực.
- Timeout tổng 180 giây; có thể cần điều chỉnh timeout provider RagHub/proxy
  để phù hợp hàng đợi. Không retry tự động để tránh tiêu quota nhiều lần.
- ZeroGPU có quota và hàng đợi; bridge không bỏ qua quota hoặc bảo đảm uptime.
- Chỉ gửi tài liệu tới Space mà bạn tin cậy; không log prompt hoặc HF token.

Chưa được triển khai lên VPS; cần URL Space cụ thể để kiểm thử end-to-end.
