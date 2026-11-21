# Qwen3-Reranker-0.6B local

## Tích hợp

- Catalog ID: `qwen3-reranker-06b`.
- Repository: `Qwen/Qwen3-Reranker-0.6B`.
- Revision: `e61197ed45024b0ed8a2d74b80b4d909f1255473`.
- Capability: RERANK, không phải model embedding hoặc chat.
- Tải khoảng 1,21 GB; manifest giới hạn 1,5 GB. Chỉ tải file cấu hình, tokenizer và
  safetensors được cho phép; không tải/chạy Python code của repository.
- Cache và trạng thái cài đặt tách theo tổ chức. Kiểm chứng manifest, kích thước
  và checksum trước khi nạp trọng số. Runtime chỉ đọc local, `trust_remote_code=False`.

Dùng adapter causal LM với template instruction chính thức và so sánh logits
`yes`/`no` ở token cuối. Không dùng adapter classification MiniLM để chấm Qwen.
Không sinh câu trả lời bằng reranker. Giữ MiniLM và các provider rerank hiện có.

Runtime đầu tiên dành cho CPU: dynamic INT8 cho Linear, batch 2 và tối đa 1024
token bao gồm instruction/query/document. Giữ prefix/suffix khi cắt. Model gốc
hỗ trợ context dài hơn nhưng bản tích hợp này chủ động giới hạn để kiểm soát
CPU/RAM. Chỉ tính logits ở vị trí cuối, không cấp phát logits toàn bộ chuỗi.
Trọng số tải về không bị sửa khi lượng tử hóa trong RAM.

## Sử dụng sau khi deploy

1. Workspace → AI & Models → Reranking.
2. Chọn `Qwen/Qwen3-Reranker-0.6B` ở mục model local.
3. Quản trị viên tổ chức tải model nếu chưa cài.
4. Chọn chế độ local, xem lại số ứng viên/kết quả/timeout rồi lưu.

Chỉ lưu cấu hình mới khi người dùng bấm lưu. Workspace cũ không có
`local_model_id` vẫn mặc định dùng MiniLM. Đổi reranker không cần reindex hay đổi
model embedding. Có thể chọn lại MiniLM hoặc tắt rerank.

API bổ sung `local_model_id` vào cấu hình workspace và `local_models` vào trạng
thái trả về. Endpoint chuẩn bị model nhận query `catalog_id`; mặc định vẫn là
MiniLM để tương thích client cũ. Chỉ chấp nhận hai catalog ID được cho phép.

Khi lưu lựa chọn Qwen, API lên lịch nạp trước trong nền cùng process để giảm cold
start. Sau khi process khởi động lại, lượt gọi đầu vẫn có thể phải nạp lại model.
Nếu quá thời gian hoặc process đang bận, luồng retrieval fallback về hybrid.
Tác vụ đã timeout dừng các batch tiếp theo; một batch CPU đang chạy không thể
bị kill ngay và vẫn giữ slot đến khi kết thúc.

## Kết quả đo ban đầu trên VPS hiện tại

Đây là chẩn đoán một số ca, chưa phải benchmark chất lượng tổng quát:

- Hai cặp đúng/sai Việt và Anh: FP32 và INT8 đều xếp đúng thứ tự.
- FP32: nạp khoảng 14 giây, hai đoạn Việt ngắn khoảng 3,1 giây.
- INT8: hai đoạn Việt ngắn khoảng 3,2 giây; cold load khoảng 26–60 giây trong
  các lượt đo có mức tải khác nhau. Peak RSS của tiến trình khoảng 4 GB, bao gồm
  lúc nạp/chuyển đổi; không coi đây là RAM thường trú chỉ của trọng số INT8.
- Với cùng 30 ứng viên thực tế của câu hỏi CNTT 2026: INT8 mất 145,87 giây
  sau khi nạp, chunk Excel đứng thứ 7. Điều này vượt timeout API tối đa 30 giây
  và chưa đưa bằng chứng đó vào top 5.

Vì vậy không dùng Qwen3 thay MiniLM mặc định trên VPS này. Form đề xuất bắt đầu
với 5 ứng viên / tối đa 5 kết quả / timeout 30 giây khi chọn Qwen. Đây là cấu hình
khởi đầu để đo, không phải cam kết mọi truy vấn đều kịp timeout. Trường hợp cần
30 ứng viên nên đánh giá hạ tầng inference nhanh hơn hoặc remote provider riêng.
Không tự tăng timeout toàn hệ thống hoặc âm thầm cắt ứng viên đã lưu.

Cần benchmark nhiều loại câu hỏi, so sánh INT8/FP32, biểu diễn bảng, độ trễ p95 và
hybrid trước/sau rerank trước khi bật cho workspace thật. Điểm yes/no không phải
xác suất câu trả lời đúng và không dùng một ngưỡng tùy ý để loại bằng chứng.

## Tham khảo

[Model card và template chính thức](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B).
