# RagHub

**Nền tảng RAG đa tổ chức để tìm kiếm và hỏi đáp trên tài liệu nội bộ.** RagHub tiếp nhận tài liệu, xử lý trong nền, truy xuất các đoạn liên quan và trả lời dạng streaming kèm trích dẫn nguồn.

RagHub là sản phẩm của **nhóm DoubleT** tham gia **Software Product Challenge (SPC) 2026** tại Trường Công nghệ Thông tin và Truyền thông, Đại học Công nghiệp Hà Nội. Mỗi tổ chức xây dựng các miền tri thức (workspace) riêng và lựa chọn AI bên ngoài hoặc mô hình chạy cục bộ theo nhu cầu.

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)
![Angular 21](https://img.shields.io/badge/Angular-21-DD0031?style=flat-square&logo=angular&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)


## Mục lục

- [Chức năng](#chức-năng)
- [Định dạng tài liệu và giới hạn](#định-dạng-tài-liệu-và-giới-hạn)
- [Công nghệ và kiến trúc](#công-nghệ-và-kiến-trúc)
- [Khởi chạy với Docker](#khởi-chạy-với-docker)
- [Triển khai self-host từ image GHCR](#triển-khai-self-host-từ-image-ghcr)
- [Thiết lập để sử dụng](#thiết-lập-để-sử-dụng)
- [Nhúng chatbot vào website](#nhúng-chatbot-vào-website)
- [AI provider và AI cục bộ](#ai-provider-và-ai-cục-bộ)
- [Bảo mật](#bảo-mật)
- [Phát triển và kiểm tra](#phát-triển-và-kiểm-tra)
- [Cấu trúc dự án](#cấu-trúc-dự-án)
- [Tài liệu chi tiết](#tài-liệu-chi-tiết)
- [Xử lý sự cố](#xử-lý-sự-cố)
- [Nhóm phát triển](#nhóm-phát-triển)

## Chức năng

| Nhóm | Khả năng | Giao diện |
| --- | --- | --- |
| Khởi tạo hệ thống | Wizard `/setup` kiểm tra hạ tầng và tạo Owner + tổ chức + membership trong một giao dịch; khóa vĩnh viễn sau khi khởi tạo (`409 INSTALLATION_ALREADY_INITIALIZED`) | Có |
| Tài khoản | Đăng nhập, refresh token xoay vòng, đổi mật khẩu, quên/đặt lại mật khẩu qua email; không có đăng ký công khai | Có |
| Tổ chức và phân quyền | Tổ chức, thành viên với vai trò `ADMIN` / `WORKSPACE_ADMIN` (giới hạn theo workspace); quyền workspace `workspace.view/edit`, `document.view/upload/reindex/delete`, `chat.use` | Có |
| Không gian làm việc | Tạo, xem, cập nhật, xóa mềm trong phạm vi tổ chức | Có |
| Tài liệu | Upload, xử lý bất đồng bộ theo giai đoạn `QUEUED → PARSING → CHUNKING → EMBEDDING → INDEXING → READY/FAILED`, theo dõi tiến độ, retry lỗi hạ tầng, lập chỉ mục lại | Có |
| Tìm kiếm | Hybrid BM25 + vector kNN, fusion RRF (`k=60`, 25 ứng viên mỗi nhánh), lọc theo tổ chức và workspace | API |
| AI provider | Cấu hình theo tổ chức, kiểm tra kết nối, mã hóa credential, đổi embedding index an toàn | Có |
| Chatbot và RAG chat | Quản lý chatbot, xuất bản, chat SSE kèm trích dẫn và thông tin sử dụng; bản nháp xem trước bằng quyền `chat.use` | Có |
| Widget nhúng | Web Component, script nhúng, origin allowlist, embed key dạng hash, rotate key, rate limit và giới hạn stream đồng thời | Có, kèm website demo |

API công bố tại [`/api/v1/docs`](http://localhost:8080/api/v1/docs) khi hệ thống chạy. Website demo widget tại [`/demo/`](http://localhost:8080/demo/).

## Định dạng tài liệu và giới hạn

Ingestion hỗ trợ **PDF, TXT UTF-8, Markdown UTF-8, DOCX, HTML (sanitized, không tải tài nguyên ngoài) và XLSX (chỉ đọc dữ liệu, không macro)**.

- PDF: ưu tiên trích xuất văn bản, bóc tách bảng bằng PyMuPDF; PDF scan cần OCR tiếng Việt/Anh (`vie+eng`) chỉ chạy khi bật `RAG_OCR_ENABLED`, mặc định tắt.
- Preflight từ chối trước embedding: quá `MAX_UPLOAD_SIZE_MB` (mặc định 25 MB nén / 100 MB giải nén), quá 70 trang PDF, quá 50 trang OCR, quá 80.000 token, quá 250 chunk, container macro-enabled hoặc sai chữ ký file.
- Lỗi hạ tầng (`STORAGE_UNAVAILABLE`, `QUEUE_UNAVAILABLE`, `EMBEDDING_UNAVAILABLE`, `INDEX_UNAVAILABLE`) được retry tự động tối đa 3 lần và cho retry thủ công; file sai định dạng hoặc OCR không được hỗ trợ yêu cầu upload lại.

## Công nghệ và kiến trúc

| Lớp | Công nghệ | Vai trò |
| --- | --- | --- |
| Giao diện | Angular 21 + TypeScript 5.9 + NG-ZORRO | Console quản trị tiếng Việt, wizard `/setup`, quản trị hệ thống `/system/ai/` |
| API | Python 3.12 + FastAPI 0.115 | Xác thực, nghiệp vụ, tìm kiếm và chat streaming |
| Engine | `raghub-core 0.1.0` | Domain, workflow RAG/ingestion/retrieval, ports; không phụ thuộc FastAPI, DB hay hạ tầng |
| Xử lý nền | Celery 5.5 + Redis 8.2 | Đọc, chia đoạn, tạo embedding, lập chỉ mục; admission rate/concurrent cho public chat |
| Dữ liệu | PostgreSQL 17.6 | Người dùng, metadata, cấu hình, trạng thái xử lý |
| Tệp và tìm kiếm | MinIO (S3) + Elasticsearch 9.1 (`vi_hybrid_v2`) | File gốc và chỉ mục hybrid |
| Gateway | NGINX 1.29 | Định tuyến, phục vụ web tĩnh, giới hạn body public 16 KiB |
| AI cục bộ tùy chọn | Sentence Transformers + Ollama 0.12 | Embedding và sinh câu trả lời trên máy |

```text
Trình duyệt ──> Nginx ──> Angular Admin / Widget / Demo
                     └──> FastAPI ──> PostgreSQL
                                   ├──> MinIO
                                   ├──> Elasticsearch
                                   └──> Redis ──> Celery worker (+ worker-ocr)
```

API và worker dùng chung mô hình dữ liệu nhưng chạy ở container riêng. File gốc nằm trong MinIO; metadata nằm trong PostgreSQL; các đoạn truy xuất nằm trong Elasticsearch. Ranh giới engine/host được ghi trong [`docs/architecture/RAGHUB_CORE_BOUNDARIES.md`](docs/architecture/RAGHUB_CORE_BOUNDARIES.md), hợp đồng ổn định trong [`docs/architecture/RAGHUB_CORE_PUBLIC_API.md`](docs/architecture/RAGHUB_CORE_PUBLIC_API.md).

## Khởi chạy với Docker

### Yêu cầu

- Docker Desktop đang chạy, Docker Compose v2.
- PowerShell cho các lệnh minh họa.
- Đủ tài nguyên cho PostgreSQL, Redis, Elasticsearch, MinIO, API, worker và web; profile `local-ai` cần thêm RAM cho mô hình.

### 1. Cấu hình môi trường

Chạy từ thư mục gốc repository:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Mở `.env` và thay tối thiểu `APP_SECRET_KEY`, `PROVIDER_MASTER_KEY` bằng hai giá trị riêng (nên ≥ 32 ký tự ngẫu nhiên). Khi chạy ngoài máy cá nhân, thay cả mật khẩu PostgreSQL và MinIO. File `.env` đã được Git bỏ qua; không commit khóa thật.

| Biến | Mục đích |
| --- | --- |
| `APP_SECRET_KEY` | Ký access token và refresh token |
| `PROVIDER_MASTER_KEY` | Mã hóa credential của AI provider |
| `POSTGRES_PASSWORD`, `DATABASE_URL` | Hai giá trị phải khớp nhau |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Thông tin truy cập MinIO |
| `BACKEND_IMAGE_TARGET` | `runtime` mặc định; `local-ai` khi cần Sentence Transformers |
| `MAX_UPLOAD_SIZE_MB` | Giới hạn upload, mặc định 25 |

Các tùy chọn khác xem trong [`.env.example`](.env.example).

### 2. Khởi động môi trường phát triển

```powershell
docker compose -f infrastructure/docker-compose.yml up --build -d --wait
docker compose -f infrastructure/docker-compose.yml ps
```

Service `migrate` chạy Alembic trước khi API khởi động. Port local mặc định chỉ bind localhost; đặt `LOCAL_BIND_ADDRESS=0.0.0.0` nếu cần truy cập LAN.

Ở môi trường này, frontend và backend mount source để hot reload: sửa `apps/admin-web/src` hoặc `backend/app` không cần build lại. Chỉ build lại khi đổi dependency hoặc Dockerfile:

```powershell
docker compose -f infrastructure/docker-compose.yml build admin-web
docker compose -f infrastructure/docker-compose.yml up -d --no-deps admin-web
```

| Địa chỉ | Dịch vụ |
| --- | --- |
| <http://localhost:8080> | Giao diện quản trị, wizard `/setup` |
| <http://localhost:8080/api/v1/docs> | OpenAPI tương tác |
| <http://localhost:8080/health/ready> | Kiểm tra PostgreSQL, Redis, Elasticsearch, MinIO |
| <http://localhost:9001> | MinIO Console |

```powershell
docker compose -f infrastructure/docker-compose.yml logs -f api worker
docker compose -f infrastructure/docker-compose.yml down
```

`down` dừng container và giữ lại volume dữ liệu.

## Triển khai self-host từ image GHCR

Repository có Compose dùng image build sẵn từ GitHub Container Registry, dùng chung [cấu hình dịch vụ](infrastructure/docker-compose.base.yml). Sau khi CI pass, push vào `develop`/`main` hoặc tag release sẽ build/publish backend (`runtime`/`local-ai`), Admin web, widget, demo và gateway.

1. Copy [`.env.self-host.example`](.env.self-host.example) thành `.env.self-host`, điền tag image đã publish, `APP_SECRET_KEY`, `PROVIDER_MASTER_KEY`, mật khẩu DB/MinIO, `FRONTEND_URL`/`PUBLIC_BASE_URL` HTTPS.
2. Chạy:

```powershell
docker compose --env-file .env.self-host -f infrastructure/docker-compose.self-host.yml --profile local-ai pull
docker compose --env-file .env.self-host -f infrastructure/docker-compose.self-host.yml --profile local-ai up -d --wait api worker nginx ollama
docker compose --env-file .env.self-host -f infrastructure/docker-compose.self-host.yml --profile local-ai run --rm ollama-init
```

3. Mở `/setup` qua HTTPS gateway để tạo Owner, tổ chức và membership.
4. Cài đặt headless dùng CLI: `docker compose ... exec api python -m app.cli bootstrap-owner --email owner@example.com`.

Chi tiết xem [cài đặt self-host](docs/operations/SELF_HOST.md) và [vận hành, backup, nâng cấp](docs/operations/SELF_HOST_OPERATIONS.md), [hướng dẫn GHCR](docs/docker-ghcr.md).

## Thiết lập để sử dụng

1. Mở `/setup` lần đầu để tạo Owner và tổ chức (hoặc dùng CLI `bootstrap-owner`). Các tài khoản tiếp theo do quản trị viên thêm, không có đăng ký công khai.
2. Tạo không gian làm việc trong tổ chức. `slug` dùng chữ thường, số và dấu `-`.
3. Trong mục Chatbot/AI, cấu hình embedding provider và chat provider, kiểm tra kết nối, rồi gắn chúng vào workspace. Xem [quy trình cấu hình AI](docs/ai-provider-layer.md).
4. Tải tài liệu lên và đợi trạng thái **READY** trước khi tìm kiếm hoặc chat.
5. Tạo và **xuất bản** chatbot, sau đó gọi chat SSE để nhận câu trả lời kèm trích dẫn.

Endpoint được bảo vệ cần `Authorization: Bearer <access_token>`. Endpoint theo tổ chức cần thêm `X-Organization-ID`. Gửi khóa AI trong trường `secret` của API provider; không đặt credential trong `config_json`.

## Nhúng chatbot vào website

Mở **Nhúng chatbot**, thêm origin chính xác của website (scheme, hostname và port), đặt màu/tiêu đề/lời chào rồi **Xuất bản chatbot**. Copy mã nhúng ngay sau lần publish đầu hoặc sau khi rotate:

```html
<script src="https://raghub.example.com/widget/raghub.js"
        data-chatbot-key="rgh_REPLACE_WITH_YOUR_KEY" async></script>
```

- Embed key xuất hiện công khai; database chỉ lưu hash. Endpoint lấy lại embed code chỉ trả `REDACTED` — cần giữ mã đã cấp hoặc rotate.
- Rotate vô hiệu hóa key cũ ngay; thay script trên mọi website sau rotate.
- Allowed origins chặn website ngoài danh sách trong trình duyệt, nhưng không thay thế xác thực người dùng vì client ngoài trình duyệt có thể giả Origin. Không đưa tài liệu riêng tư vào chatbot public nếu người ngoài không được phép xem.
- Giới hạn public mặc định (cấu hình được): **20 request/phút/IP**, **120 request/phút/chatbot**, **4 stream/chatbot**, **32 stream toàn hệ thống**, timeout stream (90 giây ở dev). Vượt giới hạn trả `429` kèm `Retry-After`; Redis lỗi trả `503`. Admin chat dùng đường riêng, không chịu các giới hạn này.

Chi tiết xem [hướng dẫn widget](docs/widget-integration.md).

## AI provider và AI cục bộ

- Embedding: `OPENAI_COMPATIBLE`, `GOOGLE_GEMINI`, `LOCAL_SENTENCE_TRANSFORMER`, `LOCAL_TOKEN_HASH` (chỉ cho phát triển/kiểm thử, không có tìm kiếm ngữ nghĩa production).
- Chat: `OPENAI_COMPATIBLE`, `GOOGLE_GEMINI`, `OLLAMA`.
- Credential được mã hóa bằng `PROVIDER_MASTER_KEY`; đổi embedding model kích hoạt lập chỉ mục lại an toàn.

Chạy AI hoàn toàn trên máy với profile `local-ai` (cài Sentence Transformers, chạy Ollama; `ollama-init` tải `OLLAMA_MODEL`, mặc định `gemma3:1b`):

```powershell
$env:BACKEND_IMAGE_TARGET = 'local-ai'
$env:OLLAMA_MODEL = 'gemma3:1b'
docker compose --env-file .env -f infrastructure/docker-compose.yml --profile local-ai up --build -d --wait
```

Sau đó tạo embedding provider `LOCAL_SENTENCE_TRANSFORMER` và chat provider `OLLAMA` với cùng tên model, gắn cả hai vào workspace. Image `runtime` mặc định không cài Sentence Transformers. Biến thể GPU có file [`infrastructure/docker-compose.gpu.yml`](infrastructure/docker-compose.gpu.yml).

## Bảo mật

- Không có đăng ký công khai; tài khoản đầu tiên qua `/setup`, các tài khoản sau do quản trị viên cấp.
- JWT access ngắn hạn (15 phút) + refresh token opaque xoay vòng, lưu dạng hash; dùng lại token đã thu hồi sẽ thu hồi toàn bộ session.
- Rate limit đăng nhập/quên mật khẩu theo IP và tài khoản; Turnstile (Cloudflare) tùy chọn cho login và quên/đặt lại mật khẩu.
- SMTP Gmail qua App Password; thiếu SMTP ở dev dùng log sender, ở môi trường khác bắt buộc cấu hình đầy đủ.
- Public widget: embed key hash, origin allowlist, rate/concurrent limit atomic qua Redis, log che key và không ghi message/IP khách.

## Phát triển và kiểm tra

### Backend

Chạy từ `backend/`:

```powershell
cd backend
python -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install -r requirements.lock
..\.venv\Scripts\python.exe -m pip install --no-deps -e ../raghub-core -e .
..\.venv\Scripts\python.exe -m alembic upgrade head
$env:PROVIDER_MASTER_KEY = 'raghub-ci-provider-key-not-for-production'
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
..\.venv\Scripts\python.exe -m ruff check . ../raghub-core
```

Core có bộ kiểm thử riêng, không cần backend hay Docker. Chạy từ `raghub-core/`:

```powershell
cd raghub-core
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
```

### Frontend

Chạy từ `apps/admin-web/`:

```powershell
cd apps/admin-web
npm ci
npm start
npm test
npm run build
```

`npm start` dùng `proxy.json` để chuyển API về backend. Test có đánh dấu `integration` cần hạ tầng Docker. Luồng chat RAG dùng [hướng dẫn smoke test](docs/rag-chat-integration.md) và script [`scripts/rag-chat-smoke.ps1`](scripts/rag-chat-smoke.ps1).

CI có job **Widget checks** (loader test Node 24, compile TypeScript 5.9) và smoke HTTP qua Nginx tới SSE cùng test atomic rate/concurrent trên Redis thật.

## Cấu trúc dự án

```text
apps/admin-web/       Ứng dụng quản trị Angular (console, /setup, /system/ai/)
apps/chat-widget/     Widget Web Component và website demo
raghub-core/          Engine độc lập (domain, application, ports, api.py)
backend/app/          API, control plane, adapter hạ tầng, worker
  composition/        Ghép use case với adapter từng runtime
  delivery/           Upload/SSE HTTP adapter và worker bootstrap
  modules/            auth, organizations, workspaces, documents, chatbots, ...
backend/alembic/      Migration cơ sở dữ liệu
backend/tests/        Kiểm thử backend
infrastructure/       Compose dev/self-host/GHCR/GPU và cấu hình Nginx
scripts/              Công cụ phát triển và smoke test
docs/                 Thiết kế, API, vận hành, tích hợp
postman/              Collection API
```

## Tài liệu chi tiết

- [API](docs/api.md) · [AI provider](docs/ai-provider-layer.md) · [RAG chat](docs/rag-chat-integration.md) · [Ingestion](docs/ingestion-qa.md)
- [Cơ sở dữ liệu](docs/database.md) · [Kiến trúc](docs/architecture.md) · [Tích hợp widget](docs/widget-integration.md)
- [Self-host](docs/operations/SELF_HOST.md) · [Vận hành self-host](docs/operations/SELF_HOST_OPERATIONS.md) · [GHCR](docs/docker-ghcr.md)
- [Quy ước đóng góp](CONTRIBUTING.md) · [Tài liệu thiết kế hệ thống](RagHub_KeHoach_TrienKhai_ThietKe_HeThong.md)

## Xử lý sự cố

- **`502 Bad Gateway` sau khi build lại web:** Nginx có thể giữ địa chỉ container cũ. Chạy `docker compose -f infrastructure/docker-compose.yml restart nginx` rồi tải lại trang.
- **Tài liệu không READY:** xem `docker compose -f infrastructure/docker-compose.yml logs -f worker api`; tra mã lỗi trong [hướng dẫn ingestion](docs/ingestion-qa.md).
- **Chat không có câu trả lời từ tài liệu:** kiểm tra provider đã gắn vào workspace, tài liệu đã READY và chatbot đã xuất bản. Xem [tích hợp RAG chat](docs/rag-chat-integration.md).

## Nhóm phát triển

**DoubleT** — Đồng Văn Tú và Nguyễn Mạnh Thi. Cố vấn: **ThS. Nguyễn Chiến Thắng**. Thông tin sản phẩm và mục tiêu cuộc thi đối chiếu từ phiếu đăng ký `DoubleT.pdf`; tính năng và lệnh chạy đối chiếu với repository hiện tại.

Các badge công nghệ sử dụng [Shields.io](https://shields.io/) và logo từ [Simple Icons](https://simpleicons.org/); cần kết nối Internet để hiển thị ảnh trong Markdown.
