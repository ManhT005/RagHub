# Docker Compose và GitHub Container Registry

## Cấu trúc

| File | Vai trò |
| --- | --- |
| `infrastructure/docker-compose.base.yml` | Environment, dependencies, healthcheck, volume và logging dùng chung; không chạy trực tiếp |
| `infrastructure/docker-compose.yml` | Local/CI: build từ source, cổng bind localhost, cấu hình Nginx bind mount |
| `infrastructure/docker-compose.ghcr.yml` | Triển khai: chỉ pull image, không build hoặc bind mount source; chỉ gateway mở cổng |
| `.env.example` | Mẫu cấu hình local |
| `.env.ghcr.example` | Mẫu cấu hình triển khai; copy thành `.env.ghcr` rồi điền giá trị |
| `.github/workflows/docker-images.yml` | Workflow build/publish tái sử dụng, được gọi sau khi CI pass |

Local giữ project `raghub` và tên volume cũ để dùng lại dữ liệu. GHCR mặc định dùng project `raghub-production` với volume riêng. Không đổi project name của một deployment đang chạy nếu muốn dùng lại volume; dùng `-p` hoặc `COMPOSE_PROJECT_NAME` phù hợp.

API, Celery worker và service `migrate` dùng cùng một image backend. Migration chạy một lần trước API, phải exit 0; API chỉ khởi động Uvicorn. Worker chờ API ready, có healthcheck riêng và 60 giây để hoàn thành task khi dừng. API readiness kiểm tra PostgreSQL, Redis, Elasticsearch và MinIO. Các service Nginx kiểm tra HTTP, Docker logs xoay vòng tối đa 3 file × 10 MB/service.

## Image được lưu trên GHCR

| Image | Nội dung |
| --- | --- |
| `ghcr.io/manht005/raghub/backend:<tag>` | API, worker và migration; target runtime |
| `ghcr.io/manht005/raghub/backend:<tag>-local-ai` | Thêm Sentence Transformers và CPU PyTorch |
| `ghcr.io/manht005/raghub/admin-web:<tag>` | Angular build và Nginx |
| `ghcr.io/manht005/raghub/chat-widget:<tag>` | JavaScript widget đã compile |
| `ghcr.io/manht005/raghub/widget-demo:<tag>` | Website demo |
| `ghcr.io/manht005/raghub/gateway:<tag>` | Nginx gateway và cấu hình routing đã đóng gói |

Workflow tự lấy repository hiện tại và chuyển tên thành chữ thường; nếu fork/đổi tên repo, đổi `RAGHUB_IMAGE_PREFIX` trong environment triển khai. PostgreSQL, Redis, Elasticsearch, MinIO và Ollama dùng image upstream đã pin. Registry lưu **image ứng dụng**, không lưu `.env`, database, tài liệu upload, AI credentials hoặc volume. Dữ liệu runtime cần backup riêng.

Image hiện build cho **linux/amd64**. Profile `local-ai` khởi động Ollama và job tải model; model embeddings/Ollama được tải lúc chạy và giữ trong volume, không nhúng vào image.

## Build và publish tự động

Workflow `CI` chạy backend, frontend, widget, ingestion/public-widget integration, migration và kiểm tra cả hai Compose. Sau khi tất cả pass:

- Pull request: build các image để kiểm tra, không login hoặc push GHCR.
- Push `develop`/`main`: publish tag `develop`/`main` và `sha-<full-commit>`.
- Push tag `v1.0.0`: publish `1.0.0`, `1.0` và `sha-<full-commit>`. Release phải nằm trong lịch sử `main`; prerelease dùng tag riêng theo metadata action.
- Run workflow thủ công: kiểm tra/build, không publish.

Backend local-ai thêm suffix `-local-ai` cho mọi tag. Không phát hành tag `latest`; triển khai bằng phiên bản đầy đủ hoặc SHA để chọn bộ image cùng commit. Cache BuildKit tách theo image/target, kèm OCI labels, SBOM và provenance. Chờ toàn bộ matrix thành công rồi mới dùng tag mới: registry không hỗ trợ publish atomic cả bộ image.

Workflow dùng `GITHUB_TOKEN` với `packages: write`; không cần tạo PAT để push từ Actions. Repo/org phải cho phép GitHub Actions và token ghi package. Image được liên kết với repository qua OCI metadata. Package mới có thể là private; muốn server pull không đăng nhập, đổi visibility từng package thành public. Xem [hướng dẫn GHCR của GitHub](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

Chỉ publish khi các thay đổi workflow đã có trên GitHub và push/merge vào nhánh được cấu hình. Các lệnh dưới đây không tự push Git repository hay thay đổi package visibility.

## Chạy local

Từ thư mục gốc repo:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose -f infrastructure/docker-compose.yml up -d --build --wait
docker compose -f infrastructure/docker-compose.yml ps -a
```

Local build dùng tag `raghub/<image>:local`, không cần GHCR credentials. Backend chỉ build tại service `api`; `worker`/`migrate` dùng lại image đó để tránh nhiều build ghi cùng tag. Trong local Compose, `api` bind mount `backend/app` và chạy Uvicorn reload; `worker` dùng cùng source mount và Watchfiles để tự restart Celery. `admin-web` dùng target development, bind mount `apps/admin-web/src` và Angular hot reload qua gateway. Sửa HTML/CSS/TypeScript/Python không cần build lại image; chỉ rebuild service tương ứng khi dependency hoặc Dockerfile thay đổi. `up --build` dùng cho lần khởi tạo hoặc khi image dependency thay đổi. Alembic source được mount vào service `migrate`, nhưng schema migration vẫn phải được chạy chủ động. Nếu chỉ chạy migration riêng trên máy mới, chạy `docker compose -f infrastructure/docker-compose.yml build api` trước. Port mặc định bind `127.0.0.1`; đặt `LOCAL_BIND_ADDRESS=0.0.0.0` nếu cần truy cập từ LAN. Dùng `--env-file .env.example` khi chạy CI hoặc môi trường test để tránh lấy cấu hình `.env` cá nhân.

Demo qua `/demo/` lấy widget từ gateway/domain hiện tại. Website demo riêng ở localhost:8081 mặc định dùng gateway localhost:8080; nếu đổi cổng/domain, thêm `?api=http://localhost:18080` vào URL demo. Origin của demo vẫn phải nằm trong allowlist chatbot.

```powershell
$env:BACKEND_IMAGE_TARGET = 'local-ai'
docker compose -f infrastructure/docker-compose.yml --profile local-ai up -d --build --wait
```

## Chạy từ GHCR

Trên máy triển khai cần Docker Compose v2 và hai file Compose base/GHCR. Có thể checkout repo; build application source không cần thiết. Gateway đã có config trong image, nên không cần copy thư mục Nginx lên server. Nếu sửa routing, build/publish image gateway cùng phiên bản mới.

```powershell
Copy-Item .env.ghcr.example .env.ghcr
# Mở .env.ghcr và điền secrets, SMTP, domain, tag đã publish.
```

Các giá trị bắt buộc: `RAGHUB_IMAGE_TAG`, `APP_SECRET_KEY`, `PROVIDER_MASTER_KEY`, `POSTGRES_PASSWORD`, `S3_SECRET_KEY`; production cũng yêu cầu SMTP hợp lệ khi backend khởi động. Dùng secrets ngẫu nhiên riêng cho từng mục. Nếu mật khẩu PostgreSQL chứa ký tự reserved của URL, đặt thêm `DATABASE_URL` với password URL-encoded, vẫn dùng password nguyên bản ở `POSTGRES_PASSWORD`.

Nếu package private, đăng nhập bằng PAT classic có `read:packages` được cấp quyền truy cập package. PAT chỉ dùng trên server cho `docker login`; không đặt trong Compose, Dockerfile hoặc repo:

```powershell
$env:GHCR_READ_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

```powershell
docker compose --env-file .env.ghcr -f infrastructure/docker-compose.ghcr.yml config --quiet
docker compose --env-file .env.ghcr -f infrastructure/docker-compose.ghcr.yml pull
docker compose --env-file .env.ghcr -f infrastructure/docker-compose.ghcr.yml up -d --wait --pull never
docker compose --env-file .env.ghcr -f infrastructure/docker-compose.ghcr.yml ps -a
```

Gateway mặc định bind localhost:8080 để đặt sau HTTPS reverse proxy của host. Nếu cần truy cập LAN trực tiếp, đặt `HTTP_BIND_ADDRESS=0.0.0.0`. DB, Redis, search, object storage, API, worker và Ollama không mở host port trong GHCR Compose. Gateway và các web service ở mạng ingress; DB/search/storage/worker ở mạng backend. API tham gia cả hai. Proxy có IP cố định `172.28.0.10`, backend chỉ tin IP đó cho rate limit; nếu đổi subnet/IP, đổi cả `PROXY_NETWORK_SUBNET`, `PROXY_IP`, `PUBLIC_CHAT_TRUSTED_PROXY_CIDRS`. Khi host reverse proxy/CDN nằm trước gateway, cấu hình real-IP theo đúng proxy tin cậy trước khi mở public; cấu hình hiện tại coi peer của gateway là IP khách.

Để dùng AI local, đặt `BACKEND_IMAGE_SUFFIX=-local-ai` trong `.env.ghcr`, rồi thêm `--profile local-ai` vào **cả pull và up**. Cả API/worker/migrate tự chọn cùng biến thể backend; các image web giữ tag thường. Profile và image variant là hai lựa chọn khác nhau, cần bật cả hai khi dùng Sentence Transformers + Ollama.

## Cập nhật, rollback và backup

Chọn `RAGHUB_IMAGE_TAG` mới, chạy `pull`, rồi `up --wait --pull never`. Compose sẽ chạy lại service migration khi image/tag đổi, trước API. Sau khi recreate API/web, restart gateway để Nginx resolve lại địa chỉ container:

```powershell
docker compose --env-file .env.ghcr -f infrastructure/docker-compose.ghcr.yml restart nginx
```

Rollback application bằng cách đặt lại tag cũ và chạy cùng quy trình. Migration database không tự downgrade khi đổi tag; kiểm tra schema tương thích hoặc restore backup đã kiểm chứng. Giữ `PROVIDER_MASTER_KEY` để đọc credentials đã mã hóa; đổi key này không phải rotate embed key.

`docker compose down` giữ volume. `down --volumes` xóa dữ liệu và chỉ dành cho stack test dùng riêng. Backup PostgreSQL, MinIO, Elasticsearch và cấu hình/secrets trên nơi lưu trữ riêng; GHCR không backup chúng. Không stamp/xóa database khi gặp revision không có trong nhánh đang dùng: chọn đúng version/schema hoặc khôi phục backup.

## Kiểm tra cấu hình

```powershell
python scripts/check-compose.py
```

Script dùng environment mẫu, không in secrets, kiểm tra local runtime/local-ai, GHCR runtime/local-ai, image dùng chung, migration gate, host ports, bind mount, trusted proxy và bắt buộc secrets/tag. Không cần Docker daemon hoặc credential registry. CI chạy script này trước bước publish. Cách Compose dùng chung cấu hình qua `extends` theo [tài liệu Docker](https://docs.docker.com/compose/how-tos/multiple-compose-files/extends/).

Kiểm tra refactor ngày 01/10/2026: local và registry-mode khởi động trên project/volume test riêng; migrate exit 0, tất cả service cần chạy healthy. Registry-mode được kiểm tra bằng image build cục bộ, không pull/push GHCR; có overlay mở DB/Redis localhost chỉ để fixture integration, không dùng khi triển khai. Ruff, actionlint, Compose validator, build cả backend runtime/local-ai và các image web/gateway pass; 157 backend test, 8 integration test và 4 widget/demo test pass. Một integration upload test skip vì chưa cấp tài khoản test. `alembic check` và `nginx -t` pass; PyTorch/Sentence Transformers import offline, cache ghi được bằng user thường. Chưa chạy workflow publish trên GitHub hoặc kiểm tra download từ GHCR.
