# Tìm kiếm theo ngữ cảnh chunk

Bổ sung ngữ cảnh vào Elasticsearch và văn bản gửi reranker để giảm việc lấy đúng
thực thể nhưng sai mục, năm hoặc loại thông tin. Không có điều kiện riêng cho một
ngành hay một đáp án, không sửa nội dung tài liệu.

## Dữ liệu lập chỉ mục

| Trường | Ý nghĩa |
| --- | --- |
| `source_title` | Tên file đã tách `_` và bỏ phần mở rộng; tín hiệu phụ |
| `section_title` | Đường dẫn tiêu đề mục |
| `table_title`, `table_headers` | Tiêu đề/caption và tên cột được giữ cùng đoạn bảng |
| `fact_years` | Các năm được nêu ở tiêu đề cột, caption hoặc tiêu đề mục gần nhất |
| `document_years` | Các năm trong tên file; không được coi là năm của mọi dữ kiện |
| `entity_codes` | Mã có chữ số trong cột được đặt tên mã/code/SKU/ID |
| `year_evidence` | Căn cứ năm: `table_headers`, `table_caption`, `heading_path`, hoặc trống |
| `context_conflicts` | Cờ khác biệt năm giữa ngữ cảnh và tên file, chưa phải kết luận tài liệu sai |
| `context_schema_version` | Phiên bản ngữ cảnh `context-v1` |

`metadata` chi tiết vẫn `enabled: false` để không tự tạo mapping tùy ý. Các trường
trên được lập chỉ mục riêng. Chúng không bổ sung trường mới vào API công khai.

`fact_years` là tín hiệu ngữ cảnh, không phải xác minh sự thật. Một bảng so sánh
2024/2025 giữ cả hai năm. Ngày của văn bản được viện dẫn trong nội dung không tự
trở thành năm của toàn chunk. Năm trong tên file không được sao chép vào
`fact_years`. Tài liệu có tên sai vẫn có thể được tìm thấy.

## Thay đổi xếp hạng

- BM25 tìm thêm tên đã chuẩn hóa, mục, tiêu đề bảng và tên cột.
- Cộng ưu tiên khi nội dung + ngữ cảnh bao phủ các từ chủ đề trong câu hỏi;
  loại bỏ một số cụm hỏi phổ biến tiếng Việt/Anh, không phân loại nghiệp vụ bằng LLM.
- Năm trong ngữ cảnh và mã định danh có điểm ưu tiên. Năm trong tên file chỉ có
  ưu tiên nhỏ nếu không có năm rõ ràng ở ngữ cảnh. Không có bộ lọc năm bắt buộc.
- Giữ nguyên bộ lọc tổ chức, workspace, trạng thái retrievable và kiểm tra READY.
- Giữ nguyên RRF, giới hạn ứng viên, số nguồn và timeout đã cấu hình.
- Reranker đọc tiêu đề mục/bảng, tên cột, nội dung và tên file. Với bảng, tối đa hai
  dòng khớp từ trong câu hỏi được đưa lên trước phần nội dung đầy đủ để giảm mất
  dòng phù hợp khi model cắt ở 512 token. Đây chỉ là biểu diễn gửi reranker;
  citation, nội dung gốc và ID chunk không bị thay đổi.
- Caption bảng được đưa vào context cho model trả lời, giữ nguyên nội dung và nguồn gốc.
- Hash cấu hình relevance có thêm phiên bản context. Artifact hiệu chỉnh cũ
  không tiếp tục được tin cậy; cần đo và hiệu chỉnh lại nếu đang bật relevance gate.

## Triển khai và dữ liệu cũ

Không cần migration PostgreSQL, không thay khóa mã hóa hay volume. Mapping mới
là bổ sung vào `vi_hybrid_v2`; truy vấn vẫn chạy khi index cũ chưa có các trường này.
Tuy nhiên, thêm mapping không tự sinh ngữ cảnh cho những chunk đã lập chỉ mục.

1. Build và kiểm thử nhánh trên môi trường thử nghiệm.
2. Dùng connection/model chọn `document_pipeline: document-v2` theo hướng dẫn
   `DOCUMENT_PROCESSING_V2.md`; tạo index version mới và chạy reindex từ tệp gốc.
3. Đối chiếu đoạn chứa đáp án, năm/chương trình và độ trễ trên cùng bộ câu hỏi.
4. Chỉ đưa index mới vào phục vụ khi đã kiểm chứng. Luồng reindex hiện tại có thể
   tự chuyển index khi job thành công, nên thực hiện thử ở workspace riêng trước.
   Giữ index version cũ để có thể rollback theo quy trình vận hành.

Reindex với pipeline legacy vẫn bổ sung trường suy ra được từ chunk, nhưng không
khôi phục được tiêu đề/cột đã bị mất khi chia bảng. Không hứa cải thiện toàn bộ dữ
liệu cũ chỉ bằng deploy code. Cấu hình rerank/top-N đã lưu ở workspace/chatbot
vẫn được giữ nguyên.

## Giới hạn và kiểm chứng

- Caption chỉ được nhận từ khối ngay trước bảng, ngắn, kết thúc bằng dấu `:` hoặc
  có đánh số mục; không nhận qua trang hay mục khác. Tiêu đề không có cấu trúc rõ
  ràng có thể bị bỏ sót.
- Chưa suy luận loại chương trình, năm ở từng ô hoặc sửa mâu thuẫn trong tài liệu.
- Không phát hiện được tài liệu sai thực tế nếu không có nguồn đối chiếu.
- Tăng chất lượng BM25 không đồng nghĩa đã chứng minh câu trả lời cuối cùng đúng;
  hybrid/RRF, reranker thực tế, ngân sách context và model trả lời vẫn cần benchmark.

Core tests kiểm tra tên sai năm, bảng nhiều năm, caption, giới hạn trang/mục và dòng
bảng. Integration tests tạo index có prefix `raghub_context_test_` trên Elasticsearch
riêng, kiểm tra điểm chuẩn/chỉ tiêu, học phí, thủ tục, mã sản phẩm và cô lập tenant;
index thử được xóa sau kiểm tra. CI khởi động ES 9.1.4 riêng cho các test này.

Chạy riêng integration tests với `RAGHUB_CONTEXT_TEST_ES_URL` trỏ đến ES dùng để
kiểm thử. Không trỏ vào ES production.
