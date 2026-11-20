# Auto-deploy develop trên VPS hiện có

Trạng thái: chỉ hoạt động sau khi merge vào develop,
cấu hình SSH/GitHub environment và bật biến `AUTO_DEPLOY_DEVELOP=true`.
Không chỉ merge vào develop rồi mặc định coi auto-deploy đã hoạt động.

## Luồng

`push develop → CI xanh + publish toàn bộ images → deploy job → SSH → pull SHA
→ verified backup → migration → health → ghi state`.

Job chỉ nhận `push` của repo chính lên `develop`, không nhận PR/fork/manual CI.
Commit cũ hơn HEAD develop được skip. Workflow và VPS đều có khóa deploy;
không hủy giữa chừng. Build trên Actions; VPS dùng GHCR `sha-<full SHA>` với
OCI revision label trùng commit. Không dùng tag develop mutable cho rollout.

## 1. Host config riêng trên VPS

Yêu cầu Python >=3.12, Docker Compose, SSH/SCP/tar và kết nối tới GHCR. Nếu package
private, deploy user phải `docker login ghcr.io` bằng quyền `read:packages` một lần.
Không gửi token registry vào workflow hoặc repo. Deploy user cần đọc env và quản lý
Docker project; SSH key này là credential có quyền vận hành VPS, chỉ dùng cho deploy.

Trong thư mục deployment hiện tại, tạo `.deploy/config.json` với quyền thư mục
700, file 600. Ví dụ cho VPS này:

```json
{
  "project": "raghub-selfhost",
  "env_file": ".env.self-host",
  "initial_compose_files": [
    "infrastructure/docker-compose.self-host.yml",
    "infrastructure/docker-compose.self-host.build.yml"
  ],
  "overlays": [],
  "health_url": "http://127.0.0.1:8080/health/ready"
}
```

Tên project phải đúng project đang chạy để giữ volume identity. `initial_compose_files`
phải mô tả cấu hình deployment cũ (có build overlay được phép). `overlays` chỉ chứa
overlay dùng cho target registry, không chứa `.build.yml`. Nếu reranking đã được
bật và model/checksum đã chuẩn bị, thêm `infrastructure/docker-compose.reranking.yml`
vào overlays, đồng thời khai báo nó trong source files ban đầu nếu stack đang dùng.
Script từ chối tự tắt reranking đang bật hoặc thay tên volume/storage image/secrets.

Lần đầu đổi image build cục bộ sang GHCR vẫn giữ project/volumes. Không thay embedding,
index hoặc model bindings. Không chạy `down -v`, prune hay tự xóa release/backup.

## 2. GitHub environment `develop-deploy`

Tạo SSH key riêng và cài public key cho deploy user trên VPS; không commit private key.
Giới hạn firewall/SSH và quyền tài khoản theo hạ tầng của bạn. Thêm environment secrets:

- `DEPLOY_HOST`: IP/hostname SSH thật của VPS, không dùng hostname CDN/proxy website.
- `DEPLOY_USER`: ví dụ `tudong`.
- `DEPLOY_PORT`: tùy chọn, mặc định 22.
- `DEPLOY_SSH_KEY`: private key tương ứng public key đã cài trên VPS.
- `DEPLOY_KNOWN_HOSTS`: dòng known_hosts đã xác minh fingerprint qua kênh tin cậy;
  cổng khác 22 cần dạng `[host]:port`. Không tự tin `ssh-keyscan` qua mạng chưa xác minh.

Environment variable `DEPLOY_ROOT=/home/tudong/RagHub`.
Repository variable `AUTO_DEPLOY_DEVELOP=true` để bật; false để ngừng các deploy mới.
Protect environment để chỉ workflow develop được phép sử dụng deploy secrets.
Nếu thêm required reviewers thì mỗi lần deploy sẽ phải approve; bỏ required reviewers
nếu muốn tự động hoàn toàn, vẫn giữ branch protection/review cho thay đổi source.

Deploy được gọi trực tiếp từ CI sau job Docker images, checkout đúng SHA của
lần push develop. Không phụ thuộc workflow_run/default branch. CI develop không
cancel giữa chừng để tránh hủy deploy/migration; PR/main vẫn dùng cancel cũ.

## 3. Lần chạy đầu và vận hành

Trước khi bật, test SSH/host fingerprint, quyền Docker, registry pull và backup trên
VPS. Không coi mock test là đã kiểm chứng toàn bộ SSH/GHCR/migration thực.

Mỗi lần deploy giải nén source đã track vào `.deploy/releases/<sha>-<id>`, không
checkout đè workspace bẩn. Secrets giữ ở env cũ; tag SHA truyền qua process env,
không sửa `.env.self-host`. State `.deploy/state.json` ghi release/tag/files hiện tại.
Sau khi chuyển sang cơ chế này, thao tác Compose thủ công phải dùng release/files/tag
trong state; không dùng `.build.yml` cũ vì có thể chạy lại image local trước đó.

Backup nhất quán dừng toàn bộ app writers (gồm OCR), dump PostgreSQL, archive offline
MinIO/ES/Redis, giữ runtime env và kiểm tra SHA256 + đọc được archive bằng pg_restore.
Model cache/Ollama cache giữ nguyên volume nhưng không nằm trong backup này.
Preflight yêu cầu ít nhất 2 GiB trống (có thể đặt `min_free_bytes` trong host config);
đây không phải ước lượng đầy đủ dung lượng snapshot cho mọi corpus.
Việc kiểm tra archive chưa tương đương restore drill end-to-end. Có downtime trong
backup/migration; đây không phải zero-downtime deployment.

## Thất bại và rollback

- Pull/identity check fail: ứng dụng cũ vẫn chạy.
- Backup fail: thử khởi động lại các service cũ; không tiếp tục migration.
- Migration hoặc health fail: writers/gateway được dừng; không tự đưa app cũ chạy
  trên schema chưa biết tương thích. Xem `.deploy/last-attempt.json` và logs riêng tư.
- Khôi phục: dùng backup đã kiểm chứng sang project mới theo runbook restore rồi
  kiểm tra và chuyển traffic; app-only rollback chỉ làm sau khi xác minh schema.

Giữ bản backup/config ở nơi hạn chế truy cập và sao lưu off-host theo chính sách
vận hành riêng. Chưa có tự động dọn backup/retention trong bản này.
