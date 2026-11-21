# Xử lý tài liệu v2 — Markdown, TXT, HTML, DOCX, XLSX và PDF/OCR

Trạng thái: thử nghiệm, opt-in. Không bật cho index đang phục vụ và không tự
reprocess dữ liệu khi deploy.

## Profile chung `document-v2`

PR này hỗ trợ tất cả định dạng hiện có qua profile `document-v2`. Parser được
chọn từ snapshot của index trước khi chạy trích xuất; chỉ parse/OCR một lần.
Host có thể resolve metadata model trước parse nhưng không gọi embedding trước
khi đã qua giới hạn file/chunk/token. Chỉ có index mới chọn profile này mới dùng
adapter v2; các adapter cũ giữ mặc định `structured=False`.

| Định dạng | Xử lý mới |
|---|---|
| Markdown | Heading hierarchy, paragraph/list/table/code blocks, header/fence lặp khi chia |
| TXT | UTF-8/BOM, CRLF, paragraph/list, dòng nguồn, từ chối NUL và encoding sai |
| HTML/HTM | Ưu tiên main; bỏ nav/footer/aside và role điều hướng; loại paragraph trùng trong cùng mục; giữ code whitespace và list đánh số |
| DOCX | Giữ thứ tự paragraph/table; đọc heading outline và list numbering; giảm lặp ô merge, giữ ký tự pipe trong cell |
| XLSX | Tách bảng bằng hàng trống, nhận diện title, giữ sheet/header/hàng thực; cảnh báo công thức không có cache, chặn grid quá thưa/lớn |
| PDF text | Thứ tự theo tọa độ/heuristic hai cột, bỏ margin lặp, trích bảng không lặp lại text của bảng, giữ trang/bbox |
| PDF scan | OCR chọn trang thiếu text hoặc text lỗi; định hướng qua Tesseract; deadline/page cap/raster cap, một luồng Tesseract, cảnh báo OCR ít text |

Chunker dùng chung không gộp khác trang hoặc file. Context embedding bao gồm
source, heading và page khi có; mọi chunk gồm context đều không quá 450 token.
Bảng lặp header và giữ row range; khối code giữ indentation. Dữ liệu nhị phân,
macro, zip bomb, sheet/page/cell limits và quota embedding vẫn được kiểm tra.
Không chạy công thức, macro, script hoặc fetch tài nguyên được nhúng trong file.

OCR cần image OCR, `RAG_OCR_ENABLED=true` và `vie+eng`/OSD của Tesseract.
Trang trống được bỏ qua; scan không được trả text thì fail thay vì đánh dấu
READY với trang thiếu nội dung. Giữ giới hạn 15 giây/trang, 50 trang OCR,
70 trang PDF, 10 phút/tài liệu; raster mới bị chặn trên 30 triệu pixel.

Cảnh báo chất lượng nằm trong metadata block/chunk, gồm
`FORMULA_WITHOUT_CACHED_VALUE`, `TABLE_SPANS_REQUIRE_REVIEW`, `OCR_LOW_TEXT`
và `LOW_TEXT_QUALITY`. PR này chưa bổ sung màn hình preview/warnings riêng.
Số lượng ô công thức chưa có cache được lưu danh sách tọa độ tối đa 100 ô;
cần tính lại workbook bằng ứng dụng spreadsheet nếu muốn index các giá trị đó.

Giới hạn: đọc hai cột và margin là heuristic, không phải mô hình hiểu layout.
HTML rowspan/colspan phức tạp được cảnh báo để review, chưa tái tạo grid đầy đủ.
DOCX list được chuẩn hóa dấu/numbering, chưa cam kết mọi kiểu multilevel Word.
XLSX tách theo hàng trống, không tự nhận diện mọi bảng đặt cạnh nhau và header
được suy đoán từ dữ liệu. OCR không có cam kết độ chính xác và chưa có deskew
ảnh tùy ý; cần corpus scan thật để đo riêng.

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

Profile `markdown-v2` hẹp vẫn dùng normalize/context như `context-v1` cho
định dạng khác. Chọn `document-v2` để dùng toàn bộ adapter mới nêu trên.

## Bật thử và bảo toàn dữ liệu

Tạo **provider connection thử nghiệm riêng**, đặt trong `config_json` rồi
đăng ký model embedding trên connection đó:

```json
{"document_pipeline": "document-v2"}
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

1. UI preview và warnings để người dùng review trước khi index.
2. Corpus thật nhiều định dạng và benchmark retrieval/cost trên index thử.
3. Cải thiện layout/bảng phức tạp theo lỗi đã đo được, không bật heuristic mù.
4. Rollout theo workspace và runbook cutover sau khi xác minh.
