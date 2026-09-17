# RagHub — khung demo

Triển khai luồng demo từ `RagHub_KeHoach_TrienKhai_ThietKe_HeThong.md`:
đăng ký/đăng nhập → workspace → upload PDF/TXT/MD → xử lý nền → hỏi đáp kèm nguồn → nhúng widget.

## Chạy bằng Docker

Bật Docker Desktop, sau đó chạy từ thư mục gốc:

```powershell
docker compose -f infrastructure/docker-compose.yml up --build -d
```

Admin: http://localhost:8080. Swagger: http://localhost:8000/docs.
Tạo tài khoản mới, mật khẩu tối thiểu 8 ký tự. Không có tài khoản mặc định.
Dữ liệu được lưu trong Docker volume `demo-data`.

## Chạy trực tiếp: Python 3.12 và Node 24

Terminal 1, từ thư mục gốc:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements.lock
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload
```

Terminal 2:

```powershell
cd apps/admin-web
npm ci
npm start
```

Mở http://localhost:4200. Token chỉ lưu trong memory; tải lại trang cần đăng nhập lại.
Giao diện demo hiện dùng tiếng Anh; tài liệu UTF-8 và câu hỏi tiếng Việt được hỗ trợ.

## Kịch bản demo

1. Đăng ký, tạo workspace “Tuyển sinh”.
2. Upload `docs/demo-tuyen-sinh.md`, chờ trạng thái READY.
3. Tạo chatbot, hỏi “Học phí bao nhiêu?”.
4. Xem trích đoạn và citation gồm tên tài liệu, số trang. **Demo dùng BM25 và trả trích đoạn, chưa dùng LLM.**
5. Publish và copy mã nhúng. Chạy `python -m http.server 8081 --directory docs` từ root, mở http://localhost:8081/widget-demo.html, nhập chatbot ID trong mã nhúng. Khi dùng Angular dev, đổi URL script trong trang mẫu từ cổng 8080 sang 4200.
6. Tạo workspace khác để kiểm tra dữ liệu không bị lẫn.
7. Thử re-index, xóa tài liệu và unpublish. Origin ngoài danh sách bị từ chối.

## Kiểm thử

```powershell
cd backend
..\.venv\Scripts\python -m pytest -q
```

Build frontend: `npm run build` trong `apps/admin-web`.
Bộ test bao phủ PDF có text/citation, upload/re-index/xóa, cách ly account/workspace, logout, publish/origin và rate limit.

## Phạm vi thực tế và phần chưa triển khai

- Angular 21.2 standalone + Signals, CSS thuần; FastAPI; SQLAlchemy + SQLite; file gốc lưu local; widget JavaScript Web Component + Shadow DOM.
- Auth dùng opaque bearer token lưu hash, TTL 1 giờ; mật khẩu scrypt. Mỗi account là một phạm vi dữ liệu riêng. Chưa có JWT/refresh, organization/membership/RBAC.
- Ingestion dùng BackgroundTasks, chưa có Celery và retry tự động. Job bị ngắt khi restart chuyển FAILED; có thể re-index thủ công. Chỉ chạy **một API worker**.
- BM25 chạy trong Python. Chưa có Elasticsearch/vector/embedding/LLM, cấu hình provider, DOCX/XLSX/PPTX, document version, Alembic, audit/usage và API key.
- Rate limit lưu memory: 20 câu/phút/IP/chatbot và 1 request đang chạy/chatbot; reset khi restart. Sau Nginx, IP là IP proxy nên khách demo chia sẻ quota.
- CORS cho localhost:4200/8080/8081. Nhúng domain khác cần sửa cả CORS và allowlist chatbot. Origin không thay thế xác thực người dùng.
- Upload tối đa 5 MB, PDF tối đa 500 trang; không OCR. Hội thoại lưu backend, chưa có UI lịch sử.
- **Chưa đạt toàn bộ Definition of Done của MVP.** Lộ trình nâng cấp ở [docs/architecture.md](docs/architecture.md).

Tham khảo kỹ thuật: [Angular compatibility](https://angular.dev/reference/versions), [FastAPI BackgroundTasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).
