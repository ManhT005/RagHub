# Thiết kế quản lý người dùng và quản trị viên workspace

## Mục tiêu

Tách quản lý tài khoản khỏi danh sách workspace. `ADMIN` quản lý toàn bộ người dùng và workspace trong tổ chức hiện tại. `WORKSPACE_ADMIN` chỉ truy cập những workspace được gán.

## Phạm vi quyền

- `ADMIN` xem, tìm kiếm, tạo, kích hoạt và vô hiệu hóa mọi tài khoản thuộc tổ chức hiện tại.
- `ADMIN` xem danh sách workspace mà từng `WORKSPACE_ADMIN` đang quản lý.
- `ADMIN` tạo workspace và thêm hoặc gỡ quản trị viên cho từng workspace.
- `WORKSPACE_ADMIN` chỉ nhìn thấy và truy cập các workspace có bản ghi trong `workspace_memberships`.
- `WORKSPACE_ADMIN` không được mở trang Quản lý người dùng, tạo workspace hoặc thay đổi phân quyền.
- Tài khoản bị vô hiệu hóa mất hiệu lực phiên đăng nhập thông qua `auth_version` và không thể đăng nhập lại.

## Điều hướng và giao diện

Sidebar thêm mục **Quản lý người dùng** cho `ADMIN`. Mục này không hiển thị với `WORKSPACE_ADMIN` và route vẫn phải có guard phía API.

Trang **Quản lý người dùng** gồm:

- ô tìm kiếm theo email;
- nút **Tạo tài khoản**;
- bảng email, trạng thái, lần đăng nhập gần nhất, ngày tạo, vai trò và các workspace đang quản lý;
- thao tác kích hoạt hoặc vô hiệu hóa;
- phân trang phía server, cố định 10 người mỗi trang;
- trạng thái tải, lỗi và danh sách trống bằng tiếng Việt.

Trang **Workspace** chỉ gồm danh sách, tìm kiếm và nút tạo workspace. Phân quyền nằm trong trang chi tiết workspace.

Tab **Quản trị viên** của workspace gồm ô tìm email, nút **Thêm quản trị viên**, danh sách quản trị viên hiện tại và thao tác **Gỡ quyền**. Khi người dùng quản lý nhiều workspace, gỡ tại một workspace chỉ xóa assignment của workspace đó.

## Quy tắc ngôn ngữ và ng-zorro

- Dùng các component ng-zorro hiện có: table, pagination, input, button, modal, tag, alert, empty và popconfirm.
- Cấu hình `NZ_I18N` bằng `vi_VN` ở cấp ứng dụng.
- Không để text mặc định tiếng Trung xuất hiện trong empty state, phân trang, modal, xác nhận hoặc thông báo.
- Các empty state quan trọng truyền nội dung tiếng Việt rõ ràng, ví dụ **Chưa có người dùng phù hợp**.

## API

Các endpoint quản trị yêu cầu access token, `X-Organization-ID` và membership `ADMIN`.

### Danh sách người dùng

`GET /api/v1/admin/users?q=&page=1&page_size=10`

Phản hồi gồm `items`, `page`, `page_size`, `total`. Mỗi item có `id`, `email`, `status`, `last_login_at`, `created_at`, `role` và danh sách workspace được gán. `page_size` giới hạn tối đa 100; giao diện luôn gửi 10.

### Tạo tài khoản

`POST /api/v1/admin/users`

Nhận email và mật khẩu ban đầu. Email được chuẩn hóa chữ thường, không cho trùng. Tài khoản mới được thêm vào tổ chức hiện tại; vai trò mặc định là `WORKSPACE_ADMIN` và chưa có workspace.

### Đổi trạng thái

`PATCH /api/v1/admin/users/{user_id}/status`

Chỉ nhận `ACTIVE` hoặc `DISABLED`. Khi vô hiệu hóa, tăng `auth_version` và thu hồi các session đang hoạt động. Không cho ADMIN tự vô hiệu hóa chính mình.

### Quản trị viên workspace

Giữ contract membership hiện tại để thêm hoặc gỡ `workspace_ids`, nhưng giao diện workspace chỉ thao tác assignment của workspace đang mở. API xác thực workspace thuộc tổ chức hiện tại.

## Xử lý lỗi

- Email trùng trả `409 USER_EMAIL_TAKEN`.
- Không tìm thấy tài khoản hoặc workspace trả `404`.
- `WORKSPACE_ADMIN` gọi API quản trị trả `403 INSUFFICIENT_PERMISSION`.
- Không cho tự vô hiệu hóa trả `409 SELF_DISABLE_NOT_ALLOWED`.
- Frontend hiển thị thông báo tiếng Việt tương ứng và giữ nguyên dữ liệu bảng khi mutation thất bại.

## Kiểm thử

- Backend kiểm tra phân trang 10 bản ghi, tìm email, tạo tài khoản, chống email trùng, kích hoạt/vô hiệu hóa, thu hồi session và giới hạn quyền.
- Backend kiểm tra `WORKSPACE_ADMIN` chỉ truy cập workspace được gán.
- Frontend kiểm tra route/sidebar theo vai trò, tham số phân trang, tìm kiếm, modal tạo tài khoản, đổi trạng thái và toàn bộ empty state tiếng Việt.
- Kiểm tra build Angular và test backend liên quan trước khi chạy full stack Docker.
