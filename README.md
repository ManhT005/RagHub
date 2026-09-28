# RagHub

**Nền tảng RAG đa tổ chức để tìm kiếm và hỏi đáp trên tài liệu nội bộ.** RagHub tiếp nhận tài liệu, xử lý trong nền, truy xuất các đoạn liên quan và cung cấp câu trả lời dạng streaming kèm trích dẫn nguồn.

RagHub là sản phẩm của **nhóm DoubleT** tham gia **Software Product Challenge (SPC) 2026** tại Trường Công nghệ Thông tin và Truyền thông, Đại học Công nghiệp Hà Nội. Dự án hướng tới một nền tảng tự phục vụ: mỗi tổ chức có thể xây dựng các miền tri thức riêng và lựa chọn AI bên ngoài hoặc mô hình chạy cục bộ theo nhu cầu.

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)
![Angular 21](https://img.shields.io/badge/Angular-21-DD0031?style=flat-square&logo=angular&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)

> **Trạng thái hiện tại:** giao diện quản trị hỗ trợ tài khoản, tổ chức, thành viên, không gian làm việc và tài liệu. Tìm kiếm, cấu hình AI provider và chatbot đã có qua API; các màn hình quản trị tương ứng chưa hoàn thiện.

## Bài toán và định hướng

Trường học cần tư vấn tuyển sinh và tra cứu quy chế; doanh nghiệp cần hỗ trợ khách hàng bằng tài liệu sản phẩm; cơ quan và tổ chức cần khai thác kho tri thức nội bộ. Xây dựng riêng một hệ thống RAG cho từng trường hợp đòi hỏi hạ tầng lưu trữ, tìm kiếm, xử lý tài liệu và tích hợp mô hình AI. RagHub gom các phần đó thành một nền tảng có phân tách dữ liệu theo tổ chức và không gian làm việc.

Theo [kế hoạch thiết kế](RagHub_KeHoach_TrienKhai_ThietKe_HeThong.md) và hồ sơ dự thi của nhóm DoubleT, MVP hướng tới luồng hoàn chỉnh: **tạo workspace → nạp tài liệu → cấu hình AI → tạo chatbot → hỏi đáp có nguồn → nhúng vào website**. Thiết kế dự kiến phục vụ cả mô hình SaaS và triển khai trên hạ tầng riêng. Repository hiện có Docker Compose cho môi trường phát triển và demo; chưa phải một bản triển khai SaaS hoặc on-premise đã được chuẩn hóa cho production.

## Mục lục

- [Bài toán và định hướng](#bài-toán-và-định-hướng)
- [Chức năng](#chức-năng)
- [Mục tiêu MVP còn lại](#mục-tiêu-mvp-còn-lại)
- [Công nghệ và kiến trúc](#công-nghệ-và-kiến-trúc)
- [Khởi chạy với Docker](#khởi-chạy-với-docker)
- [Thiết lập để sử dụng](#thiết-lập-để-sử-dụng)
- [AI cục bộ](#ai-cục-bộ)
- [Phát triển và kiểm tra](#phát-triển-và-kiểm-tra)
- [Cấu trúc dự án](#cấu-trúc-dự-án)
- [Xử lý sự cố và tài liệu](#xử-lý-sự-cố-và-tài-liệu)
- [Nhóm phát triển](#nhóm-phát-triển)

## Chức năng

| Nhóm | Khả năng hiện có | Giao diện web |
| --- | --- | --- |
| Tài khoản và phân quyền | Đăng ký, đăng nhập, JWT; tổ chức, thành viên và vai trò `OWNER` / `ADMIN` / `EDITOR` / `VIEWER` | Có |
| Không gian làm việc | Tạo, xem, cập nhật và xóa mềm trong phạm vi tổ chức | Một phần: tạo và xem |
| Tài liệu | Upload PDF/TXT/Markdown, xử lý bất đồng bộ, theo dõi tiến độ, retry và lập chỉ mục lại | Có |
| Tìm kiếm | BM25 kết hợp vector, lọc theo tổ chức và không gian làm việc | API |
| AI provider | Cấu hình theo tổ chức, kiểm tra kết nối, mã hóa credential và đổi embedding index an toàn | API |
| Chatbot và RAG chat | Quản lý chatbot, chat SSE, trả lời kèm trích dẫn và thông tin sử dụng | API |

API công bố tại [`/api/v1/docs`](http://localhost:8080/api/v1/docs) khi hệ thống chạy. Mục Chatbot trong thanh điều hướng web hiện bị vô hiệu hóa.

### Giới hạn định dạng hiện tại

Ingestion đang nhận **PDF có văn bản chọn được, TXT UTF-8 và Markdown UTF-8**. PDF scan cần OCR sẽ bị từ chối; DOCX, XLSX và PPTX xuất hiện trong kế hoạch MVP nhưng chưa có parser trong repository. Việc ghi rõ phạm vi này giúp tránh nhầm lẫn giữa thiết kế và tính năng đang chạy.

## Mục tiêu MVP còn lại

Tài liệu thiết kế phiên bản 1.0 đặt mốc MVP ngày **08/10/2026**. Các hạng mục sau thuộc mục tiêu đó và **chưa được triển khai đầy đủ trong mã nguồn hiện tại**:

| Hạng mục theo kế hoạch | Trạng thái hiện tại |
| --- | --- |
| Parser DOCX, XLSX, PPTX | Chưa có; ingestion đang hỗ trợ PDF, TXT và Markdown |
| Giao diện cấu hình AI provider và chatbot | API đã có; giao diện quản trị chưa có |
| Chat Widget dạng Web Component, script nhúng và website mẫu | Chưa có trong `apps/` |
| Allowed Origins, API key cho tích hợp, rate limit và giới hạn chat đồng thời | Chưa có luồng public widget/API tương ứng |
| Quy trình triển khai SaaS và on-premise hoàn chỉnh | Docker Compose đã có cho phát triển và demo; chưa có quy trình production |

Mốc trên là **mục tiêu của tài liệu kế hoạch**, không phải tuyên bố MVP đã hoàn thành. [Tài liệu thiết kế hệ thống](RagHub_KeHoach_TrienKhai_ThietKe_HeThong.md) mô tả chi tiết kiến trúc, backlog, tiêu chí nghiệm thu và kịch bản demo dự kiến.

## Công nghệ và kiến trúc

| Lớp | Công nghệ | Vai trò |
| --- | --- | --- |
| Giao diện | ![Angular](https://img.shields.io/badge/Angular-21-DD0031?style=flat-square&logo=angular&logoColor=white) ![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat-square&logo=typescript&logoColor=white) | Ứng dụng quản trị tiếng Việt với NG-ZORRO |
| API | ![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white) | Xác thực, nghiệp vụ, tìm kiếm và chat streaming |
| Xử lý nền | Celery 5.5 + ![Redis](https://img.shields.io/badge/Redis-8.2-DC382D?style=flat-square&logo=redis&logoColor=white) | Đọc, chia đoạn, tạo embedding và lập chỉ mục tài liệu |
| Dữ liệu | ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17.6-4169E1?style=flat-square&logo=postgresql&logoColor=white) | Người dùng, metadata, cấu hình và trạng thái xử lý |
| Tệp và tìm kiếm | ![MinIO](https://img.shields.io/badge/MinIO-S3-C72E49?style=flat-square&logo=minio&logoColor=white) ![Elasticsearch](https://img.shields.io/badge/Elasticsearch-9.1-005571?style=flat-square&logo=elasticsearch&logoColor=white) | Tệp gốc và chỉ mục tìm kiếm |
| Triển khai cục bộ | ![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white) ![NGINX](https://img.shields.io/badge/NGINX-1.29-009639?style=flat-square&logo=nginx&logoColor=white) | Chạy và định tuyến các dịch vụ |
| AI cục bộ tùy chọn | Sentence Transformers + ![Ollama](https://img.shields.io/badge/Ollama-0.12-111111?style=flat-square&logo=ollama&logoColor=white) | Embedding và sinh câu trả lời trên máy |

```text
Trình duyệt ──> Nginx ──> Angular Admin
                    └──> FastAPI ──> PostgreSQL
                                  ├──> MinIO
                                  ├──> Elasticsearch
                                  └──> Redis ──> Celery worker
```

API và worker dùng chung mô hình dữ liệu nhưng chạy ở hai container riêng. File gốc nằm trong MinIO; metadata nằm trong PostgreSQL; các đoạn tài liệu để truy xuất nằm trong Elasticsearch. Xem [tài liệu kiến trúc](docs/architecture.md) để biết luồng xử lý chi tiết.

## Khởi chạy với Docker

### Yêu cầu

- Docker Desktop đang chạy và có Docker Compose v2.
- PowerShell để dùng các lệnh và script minh họa bên dưới.
- Tài nguyên đủ cho PostgreSQL, Redis, Elasticsearch, MinIO, API, worker và web; profile `local-ai` cần thêm bộ nhớ để chạy mô hình.

### 1. Cấu hình môi trường

Chạy từ thư mục gốc repository:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Mở `.env` và thay tối thiểu `APP_SECRET_KEY` cùng `PROVIDER_MASTER_KEY` bằng hai giá trị riêng. Khi chạy ngoài môi trường phát triển cá nhân, cần thay cả mật khẩu PostgreSQL và MinIO. File `.env` đã được Git bỏ qua; không commit khóa hoặc mật khẩu thật.

| Biến | Mục đích |
| --- | --- |
| `APP_SECRET_KEY` | Ký access token và refresh token |
| `PROVIDER_MASTER_KEY` | Mã hóa credential của AI provider |
| `POSTGRES_PASSWORD`, `DATABASE_URL` | Mật khẩu và chuỗi kết nối PostgreSQL; hai giá trị phải khớp |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Thông tin truy cập MinIO |
| `BACKEND_IMAGE_TARGET` | `runtime` mặc định; dùng `local-ai` khi cần Sentence Transformers |
| `MAX_UPLOAD_SIZE_MB` | Giới hạn dung lượng tài liệu, mặc định 25 MB |

Các tùy chọn khác và giá trị phát triển mẫu có trong [`.env.example`](.env.example).

### 2. Khởi động

```powershell
docker compose -f infrastructure/docker-compose.yml up --build -d --wait
docker compose -f infrastructure/docker-compose.yml ps
```

Compose tự chạy migration Alembic trước khi API nhận yêu cầu. Lần đầu có thể mất vài phút để tải image và khởi tạo dữ liệu.

| Địa chỉ | Dịch vụ |
| --- | --- |
| <http://localhost:8080> | Giao diện quản trị |
| <http://localhost:8080/api/v1/docs> | Tài liệu OpenAPI tương tác |
| <http://localhost:8080/health/ready> | Kiểm tra PostgreSQL, Redis, Elasticsearch và MinIO |
| <http://localhost:9001> | MinIO Console |

Để xem log hoặc dừng stack:

```powershell
docker compose -f infrastructure/docker-compose.yml logs -f api worker
docker compose -f infrastructure/docker-compose.yml down
```

`down` dừng container và giữ lại các volume dữ liệu.

## Thiết lập để sử dụng

1. Mở giao diện quản trị, tạo tài khoản bằng email hợp lệ và mật khẩu từ 8 ký tự.
2. Tạo tổ chức và không gian làm việc. `slug` dùng chữ thường, số và dấu `-`.
3. Dùng API để tạo embedding provider và chat provider, kiểm tra kết nối, rồi gắn chúng vào không gian làm việc. Xem [quy trình cấu hình AI](docs/ai-provider-layer.md).
4. Tải tài liệu lên và đợi trạng thái **Sẵn sàng** trước khi tìm kiếm hoặc dùng chatbot.
5. Tạo, xuất bản chatbot và gọi API chat để nhận các sự kiện SSE cùng trích dẫn nguồn.

Endpoint được bảo vệ cần header `Authorization: Bearer <access_token>`. Endpoint theo tổ chức cần thêm `X-Organization-ID`. Gửi khóa AI trong trường `secret` của API provider; không đặt credential trong `config_json`.

RagHub hỗ trợ `OPENAI_COMPATIBLE`, `GOOGLE_GEMINI`, `LOCAL_SENTENCE_TRANSFORMER` và `LOCAL_TOKEN_HASH` cho embedding, cùng `OPENAI_COMPATIBLE`, `GOOGLE_GEMINI` và `OLLAMA` cho chat. `LOCAL_TOKEN_HASH` chỉ phục vụ phát triển và kiểm tra tích hợp, không cung cấp tìm kiếm ngữ nghĩa chất lượng sản xuất.

## AI cục bộ

Profile `local-ai` cài Sentence Transformers và chạy Ollama. Lần khởi động đầu, dịch vụ `ollama-init` tải `OLLAMA_MODEL` vào volume dùng chung.

```powershell
$env:BACKEND_IMAGE_TARGET = 'local-ai'
$env:OLLAMA_MODEL = 'gemma3:1b'
docker compose --env-file .env -f infrastructure/docker-compose.yml --profile local-ai up --build -d --wait
```

Sau đó tạo embedding provider loại `LOCAL_SENTENCE_TRANSFORMER`, chat provider loại `OLLAMA` với cùng tên model, và gắn cả hai vào không gian làm việc. Image `runtime` mặc định không cài Sentence Transformers. Hướng dẫn cấu hình và cơ chế lập chỉ mục lại khi đổi model nằm trong [docs/ai-provider-layer.md](docs/ai-provider-layer.md).

## Phát triển và kiểm tra

### Backend

Chạy các lệnh sau từ `backend/`:

```powershell
cd backend
python -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install -r requirements.lock
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
..\.venv\Scripts\python.exe -m ruff check .
```

### Frontend

Chạy các lệnh sau từ `apps/admin-web/`:

```powershell
cd apps/admin-web
npm ci
npm start
npm test
npm run build
```

`npm start` dùng `proxy.json` để chuyển yêu cầu API đến backend. Các bài kiểm thử backend được đánh dấu `integration` cần hạ tầng Docker. Để kiểm tra luồng chat RAG với provider thật hoặc cục bộ, xem [hướng dẫn smoke test](docs/rag-chat-integration.md) và script [`rag-chat-smoke.ps1`](scripts/rag-chat-smoke.ps1).

## Cấu trúc dự án

```text
apps/admin-web/       Ứng dụng quản trị Angular
backend/app/          API, nghiệp vụ, adapter hạ tầng và worker
backend/alembic/      Migration cơ sở dữ liệu
backend/tests/        Kiểm thử backend
infrastructure/       Docker Compose và cấu hình Nginx
scripts/              Công cụ hỗ trợ phát triển và smoke test
docs/                 Tài liệu thiết kế, API và hướng dẫn tích hợp
```

## Xử lý sự cố và tài liệu

- **`502 Bad Gateway` sau khi build lại web:** Nginx có thể vẫn giữ địa chỉ container cũ. Chạy `docker compose -f infrastructure/docker-compose.yml restart nginx` rồi tải lại trang.
- **Tài liệu không đến trạng thái Sẵn sàng:** xem `docker compose -f infrastructure/docker-compose.yml logs -f worker api`; tra mã lỗi xử lý trong [hướng dẫn ingestion](docs/ingestion-qa.md).
- **Chat không có câu trả lời dựa trên tài liệu:** kiểm tra provider đã gắn vào workspace, tài liệu đã sẵn sàng và chatbot đã xuất bản. Xem [tích hợp RAG chat](docs/rag-chat-integration.md).

Tài liệu chi tiết: [API](docs/api.md) · [AI provider](docs/ai-provider-layer.md) · [Cơ sở dữ liệu](docs/database.md) · [Quy ước đóng góp](CONTRIBUTING.md).

## Nhóm phát triển

**DoubleT** — Đồng Văn Tú và Nguyễn Mạnh Thi. Cố vấn: **ThS. Nguyễn Chiến Thắng**. Thông tin sản phẩm và mục tiêu cuộc thi được đối chiếu từ phiếu đăng ký `DoubleT.pdf`; các tính năng và lệnh chạy được đối chiếu với repository hiện tại.

Các badge công nghệ sử dụng [Shields.io](https://shields.io/) và logo từ [Simple Icons](https://simpleicons.org/); cần kết nối Internet để hiển thị ảnh trong Markdown.
