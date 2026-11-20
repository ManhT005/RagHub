# Kết nối Hugging Face Spaces dùng chung

Trong **Thêm AI provider**, chọn **Hugging Face Spaces**. Đây là kết nối trực tiếp
Gradio, không dùng Inference Router hoặc bridge server riêng.

1. Nhập URL `https://huggingface.co/spaces/owner/name` hoặc origin `https://…hf.space`.
2. Nhập HF token nếu cần vào **API key** (mã hóa theo cơ chế credentials hiện có).
3. Với SICT, chỉ nhập link rồi bấm **Kiểm tra kết nối & tìm model**: backend tự
   cấu hình endpoint query/document, danh sách model tự điền dimension 1024.
   Vẫn phải bấm **Kiểm tra & đăng ký model** để xác nhận inference thực thành công.
4. Space chưa có preset: mở **Cấu hình nâng cao**, bấm **Đọc API Space** để xem API.
5. Chọn endpoint Chat hoặc cả hai endpoint embedding query/document. Điều chỉnh
   mapping JSON; không có cách suy luận an toàn chức năng của mọi endpoint.
6. Kiểm tra kết nối, chọn `space-chat` hoặc `space-embedding`. Với Space embedding
   không có preset, nhập dimension cố định trong nâng cao. Runtime kiểm tra vector thực.

Mapping gồm `api`, `inputs` (array theo đúng thứ tự tham số), `output` (đường dẫn
trong array kết quả Gradio; mặc định `0`). Ví dụ:

```json
{"api":"predict","inputs":["$prompt",[],512,0.7],"output":"0"}
```

Chat hỗ trợ `$prompt` (lịch sử ghép thành text có nhãn role) hoặc `$messages`
(array role/content). Dùng `$messages` khi Space hỗ trợ phân tách role; `$prompt`
không tương đương system role của API native. Output phải chọn được một chuỗi.

Embedding hỗ trợ `$text`, `$texts` (array một text), `$dimension`, `$task`
(`query`/`document`). Gọi tuần tự từng text để hỗ trợ cả single-input endpoint;
không có retry tự động và chưa tối ưu batching.

## Preset SICT

HF token được nhập/thay trong ô **API key** của connection; để trống khi chỉnh sửa
thì giữ token đã lưu, không hardcode token vào preset. Token mới cùng tài khoản
không tăng quota. Khi có token tài khoản còn quota, đăng ký/test model trước rồi
mới retry các tài liệu đã thất bại; bản sửa không tự retry hoặc reindex dữ liệu cũ.

SICT có thể trả HTTP 200 và event `complete` nhưng payload `status=error`.
Adapter kiểm tra phản hồi lỗi trước khi đọc `embeddings`; lỗi quota được phân loại
`PROVIDER_RATE_LIMITED`, lỗi xác thực là `PROVIDER_AUTH_FAILED`. Nội dung lỗi gốc
không được chuyển nguyên văn ra UI để tránh lộ thông tin. Test 1024 chiều dùng
mock cả query/document; chưa xác nhận inference thật khi tài khoản hết quota.

Nút preset chỉ điền URL và hai mapping, không tự lưu hoặc gọi GPU:

```json
{"api":"embed_batch_text","inputs":["$texts","query","$dimension"],"output":"0.embeddings"}
```

Document dùng cùng endpoint và thay `query` bằng `document`. Đăng ký dimension
1024 nếu dùng cấu hình mặc định của SICT. Preset vẫn phải test API/model thực.

## Giới hạn và dữ liệu

Chỉ hỗ trợ modern Gradio queue API text/JSON; không hỗ trợ mọi Space, file upload,
tool calls, rerank hoặc API legacy. Stream chat trả một kết quả sau khi job hoàn tất.
Timeout job 180 giây, response tối đa 16 MB; quota/hàng đợi thuộc tài khoản HF.
Không theo redirect hoặc cho nhập origin ngoài HF. Không trả nội dung lỗi upstream
ra UI. Không tự đăng ký model từ tên Space hoặc tải model về VPS.

Không migration, không đổi provider của workspace cũ. Thử bằng workspace mới;
đổi embedding model bắt buộc lập lại index dù dimension trùng. Nội dung gửi xử lý
sẽ ra Space bên ngoài. Kiểm tra license model/Space (SICT công bố phi thương mại).
Test giao thức dùng mock, chưa xác nhận live GPU inference.

PR này thay đề xuất SICT bridge riêng; không cần merge PR SICT trước. Standalone
chat bridge cũ vẫn được giữ tương thích, nhưng luồng mới không cần triển khai nó.
