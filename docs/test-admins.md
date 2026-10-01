# Hai tài khoản quản trị test dùng chung

Tài khoản nằm trong PostgreSQL của máy triển khai. GHCR chỉ lưu chương trình seed,
không lưu database hay mật khẩu. Hai tài khoản được cấp quyền `ADMIN` trong cùng
organization `raghub-shared-test`, với workspace `shared-test`.

## Chuẩn bị thông tin đăng nhập

Tạo file `.env.test-admins.json` trên máy triển khai (đã được Git ignore):

```json
{
  "organization_slug": "raghub-shared-test",
  "organization_name": "RagHub Shared Test",
  "accounts": [
    {"email": "admin1@raghub.example.com", "password": "<mat-khau-rieng-it-nhat-12-ky-tu>"},
    {"email": "admin2@raghub.example.com", "password": "<mat-khau-rieng-it-nhat-12-ky-tu>"}
  ]
}
```

Chia sẻ file qua kênh riêng cho người test. Không commit file hoặc đưa vào Docker image.
Email mẫu dùng để đăng nhập; chức năng quên mật khẩu cần địa chỉ email nhận được thư.

## Insert trên máy triển khai GHCR

Sau khi deployment đã chạy migration, đặt `RAGHUB_SEED_IMAGE` thành image backend
chứa `app.seed_test_admins`. Có thể dùng tag seed riêng mà không đổi tag ứng dụng.
Chạy tại thư mục gốc repo, với đúng `.env.ghcr` và project name của deployment:

```powershell
$env:RAGHUB_SEED_IMAGE = 'ghcr.io/manht005/raghub/backend:test-admins-<commit>'
docker compose --env-file .env.ghcr -f infrastructure/docker-compose.ghcr.yml -f infrastructure/docker-compose.seed-test-admins.yml pull seed-test-admins
Get-Content -Raw -Encoding UTF8 .env.test-admins.json | docker compose --env-file .env.ghcr -f infrastructure/docker-compose.ghcr.yml -f infrastructure/docker-compose.seed-test-admins.yml run --rm --no-deps -T seed-test-admins
```

Trên Linux:

```sh
export RAGHUB_SEED_IMAGE=ghcr.io/manht005/raghub/backend:test-admins-<commit>
docker compose --env-file .env.ghcr -f infrastructure/docker-compose.ghcr.yml -f infrastructure/docker-compose.seed-test-admins.yml pull seed-test-admins
docker compose --env-file .env.ghcr -f infrastructure/docker-compose.ghcr.yml -f infrastructure/docker-compose.seed-test-admins.yml run --rm --no-deps -T seed-test-admins < .env.test-admins.json
```

Lệnh trả về email, quyền, organization/workspace ID và kết quả `created` hoặc
`unchanged`, không in mật khẩu. Đăng nhập bằng hai tài khoản rồi chọn organization
**RagHub Shared Test**. Cả hai dùng chung dữ liệu của organization này.

Lệnh không tự chạy lúc khởi động. Chạy lại giữ nguyên mật khẩu và quyền hiện tại;
nếu email đã tồn tại nhưng không phải ADMIN active của organization test, lệnh từ
chối và rollback toàn bộ. Đổi mật khẩu bằng chức năng đổi mật khẩu sau đăng nhập.
Để ngừng dùng tài khoản test, đặt trạng thái tài khoản thành `DISABLED`.
