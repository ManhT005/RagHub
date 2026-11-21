# Xử lý tài liệu v2 — PR đầu tiên: Markdown

Trạng thái: thử nghiệm, opt-in. Không bật cho index đang phục vụ và không tự
reprocess dữ liệu khi deploy.

## Khảo sát baseline

Pipeline hiện có `ParsedBlock` cho heading, paragraph, list, table và code.
DOCX/HTML/XLSX đã dùng một phần contract này. Markdown cũ chỉ tách section theo
ATX heading; không giữ cấp heading và không nhận diện list/code thành block.
Chunker chung có thể cắt code hoặc quy trình theo token, và chỉ nhận bảng khi
bảng đứng đầu section. Các pipeline `legacy`, `normalized-v1`, `context-v1`
phải giữ cách xử lý cũ để index đang dùng không đổi ngầm.

Benchmark retrieval trước thay đổi trên RAGHub có hai câu chưa tìm được nhãn
bằng chứng trong top 5: chuỗi trạng thái ingestion và phân biệt hai khóa cấu
hình. Đây là tín hiệu để kiểm tra cấu trúc bảng/list, chưa chứng minh parser
là nguyên nhân hoặc pipeline mới sẽ sửa được kết quả retrieval.

## Phạm vi `markdown-v2`

- Nhận diện heading ATX/Setext và giữ breadcrumb; heading trong fenced code
  không được xem là heading tài liệu.
- Nhận diện paragraph, pipe table, list và fenced code. Không chạy code, YAML,
  macro hay tải tài nguyên từ tài liệu.
- Bỏ front matter đầu file khi có delimiter và key/value; chỉ giữ title dạng
  text làm metadata, không dùng YAML loader.
- Giữ list item với các dòng con khi có thể. Gộp các paragraph liền nhau cùng
  mục; khối quá lớn được chia có đánh dấu `structural_split`.
- Lặp header bảng và fence code khi chia; code giữ indentation, list giữ ký
  hiệu thứ tự. Fence tái tạo được đánh dấu `synthetic_fences`.
- Embedding thêm tên file và đường dẫn heading. Ngân sách 450 token bao gồm
  cả context này; không chỉ tính body.
- Lưu block type, line range của block nguồn, section line và unit range trong
  block để truy vết. Line range là phạm vi block, chưa phải exact character
  spans của từng fragment. Parent của heading lặp được phân biệt theo dòng.
- Giữ UUID theo version tài liệu và liên kết previous/next chunk ổn định.

Không phải parser đầy đủ CommonMark/GFM: blockquote, HTML trong Markdown,
indented code ngoài fenced block, YAML phức tạp và cấu trúc lồng sâu chưa có
xử lý ngữ nghĩa riêng. Nội dung chưa nhận diện vẫn được giữ như paragraph.
Một hàng bảng quá lớn bị từ chối rõ ràng thay vì cắt hỏng cột; cần thu gọn/chia
hàng đó trước khi dùng pipeline này. Front matter không đóng được giữ nguyên.

Với định dạng khác, lựa chọn này dùng normalize/context như `context-v1`;
không bổ sung thuật toán PDF/OCR/DOCX/XLSX trong PR đầu tiên.

## Bật thử và bảo toàn dữ liệu

Trong cấu hình **model embedding mới**, đặt:

```json
{"document_pipeline": "markdown-v2"}
```

Không sửa cấu hình trực tiếp trong database hoặc đổi tên profile của active
index. Pipeline là thành phần của embedding fingerprint; model registration
mới với profile mới sẽ yêu cầu index version mới qua luồng đổi model/reindex
hiện có. Thử trước trên workspace bản sao, giữ model, tập câu hỏi và cấu hình
reranking cố định. Chỉ cutover khi index mới được xác minh.

Để rollback trước cutover, tiếp tục dùng index cũ. Sau cutover cần dùng luồng
đổi model/index được hỗ trợ và xác minh lại; không hứa rollback tức thì bằng
một biến env. Không xóa file gốc, volume hay index cũ trong PR này.

## Xác minh

Kiểm thử bao gồm heading hierarchy, thứ tự block và dòng nguồn, Unicode,
code dài/indentation/fence, list lồng, bảng nhiều hàng/header lặp, hàng quá
lớn, heading trùng tên, liên kết chunk và opt-in qua ingestion use case.
Fixture `backend/tests/fixtures/document_processing/markdown_v2.md` chứa quy
trình, bảng trạng thái và ví dụ khóa giả để kiểm tra các dạng bị mất ngữ cảnh.

Dry-run chỉ đọc trên 21 file Markdown gốc của workspace RAGHub:

| Chỉ số | Legacy | Markdown v2 |
|---|---:|---:|
| Số chunk | 370 | 497 |
| Token embedding tổng | 38.019 | 54.589 |
| Embedding token lớn nhất/chunk mới | — | 431 / giới hạn 450 |
| Lỗi parse/chunk | 0 | 0 |

Token embedding tăng khoảng 43,6% do context và tách block. Đây là phép đo
cấu trúc/chi phí, **không phải kết quả cải thiện retrieval**. Không gọi API
embedding, không ghi ES và không thay đổi cấu hình workspace trong dry-run.
Trước khi bật rộng, cần review nhãn trên index mới và chạy lại Hit/MRR/nDCG,
thời gian ingestion, tài nguyên và chi phí với cùng corpus.

## Các PR tiếp theo

1. Review preview/quality warnings và thực nghiệm retrieval trên index thử.
2. HTML: main-content extraction và boilerplate; DOCX: thứ tự văn bản/bảng.
3. XLSX: nhận diện bảng và header; PDF text: layout/margin; OCR: selective OCR.
4. UI báo chất lượng parse, rollout và runbook cutover theo từng định dạng.
