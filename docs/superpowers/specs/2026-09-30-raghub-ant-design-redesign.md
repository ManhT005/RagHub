# RagHub Ant Design Redesign

## Mục tiêu

Tái triển khai giao diện web RagHub theo hình mẫu người dùng cung cấp, dùng Angular 21 và NG-ZORRO 21. Giữ các API và nghiệp vụ hiện hữu; giao diện phải vận hành được với dữ liệu thật thay vì chỉ là bản minh hoạ tĩnh.

## Phạm vi

- Landing page công khai tại `/` với hero, CTA, minh hoạ hệ sinh thái tri thức và bốn năng lực RAG.
- Khu vực quản trị tách tại `/app`, gồm Tổng quan, Workspace, Tài liệu, Chatbot và Cài đặt chatbot.
- Layout quản trị dùng sidebar, header tài khoản/thông báo và vùng nội dung nhất quán.
- Các màn hình dùng component NG-ZORRO cho layout, menu, card, bảng, form, upload, tab, modal, avatar, badge, pagination và feedback.
- Có loading, empty state, error state và responsive navigation.

## Không thuộc phạm vi

- Thay đổi API backend, schema, quyền truy cập hoặc cơ chế RAG.
- Phát triển widget public mới ngoài phần hiển thị/copy cấu hình embed đang có trong API.
- Thay thế các provider AI hoặc ingestion parser.

## Hệ thống thiết kế

Nền trang là `#F6FAFF`; surface là `#FFFFFF`; màu chữ chính là `#0E2B61`; màu hành động chính là `#1677FF`; border là xanh-xám nhạt. Card bo góc 10–12px, có viền mảnh và bóng rất nhẹ. Typography dùng Inter/system sans-serif, ưu tiên câu ngắn, tiếng Việt sentence case và độ tương phản AA.

Giao diện lấy bố cục từ ảnh mẫu: landing có hero trái, minh hoạ phải; admin có sidebar hẹp ở trái, header trên, card thông tin mảnh và khoảng trắng rộng. Không dùng gradient nặng, badge viết hoa hoặc card đồng hạng hàng loạt khi thông tin có cấp bậc khác nhau.

## Kiến trúc frontend

Tạo `PublicLayoutComponent` cho landing/auth và `AdminLayoutComponent` cho các route quản trị. Layout admin sở hữu sidebar, header, hành vi chọn menu và responsive drawer; feature components chỉ sở hữu nội dung nghiệp vụ. Các phần lặp lại được tách thành các component trình bày nhỏ: stat card, activity feed, quick action, workspace card, document toolbar/table, chatbot list/conversation và embed panel.

`RagHubApiService` tiếp tục là nguồn dữ liệu. Feature component chuyển response thành view-model cục bộ khi cần định dạng nhãn, icon hoặc trạng thái; không làm biến đổi hợp đồng API. Khi API trả về tập rỗng, trang hiển thị empty state có CTA; không tạo bản ghi giả.

## Routes

| Route | Màn hình | Yêu cầu |
| --- | --- | --- |
| `/` | Landing | CTA bắt đầu/đăng nhập; đã có phiên thì dẫn tới `/app/overview`. |
| `/auth` | Xác thực | Giữ luồng login/register hiện có. |
| `/app/overview` | Tổng quan | Thống kê, hoạt động gần đây, tác vụ nhanh. |
| `/app/workspaces` | Workspace | Danh sách workspace, tạo mới, mở workspace console. |
| `/app/documents` | Tài liệu | Chọn workspace, tìm/lọc, upload, table, phân trang, retry/xóa. |
| `/app/chatbots` | Chatbot | Danh sách chatbot, tạo/quản lý, khung chat streaming. |
| `/app/chatbots/:id/settings` | Cài đặt chatbot | Tab chung, nguồn tri thức, AI & mô hình, bảo mật, nhúng mã. |

Các route cũ (`/workspaces`, `/documents`, `/chatbots`, `/settings`) redirect có chủ đích vào đường dẫn `/app` tương ứng, không được redirect nhầm giữa các module.

## Màn hình

### Landing

Hero giới thiệu khả năng xây chatbot trên dữ liệu riêng. CTA chính là “Bắt đầu ngay”, CTA phụ là “Tìm hiểu thêm”. Dải năng lực ở cuối mô tả RAG chính xác, đa định dạng, linh hoạt AI và triển khai dễ dàng. Minh hoạ được đóng gói thành asset/component riêng để không phụ thuộc nội dung dashboard.

### Tổng quan

Hiển thị bốn chỉ số: domain/workspace, tài liệu, chatbot và lượt truy vấn. Hoạt động gần đây có icon theo loại sự kiện và thời gian; action panel dẫn đến đúng các thao tác tạo workspace, tải tài liệu, tạo chatbot và nhúng chatbot.

### Workspace

Mỗi workspace là card/list item có icon, tên, loại, số tài liệu, số chatbot, thời gian cập nhật và menu ngữ cảnh. Nút tạo mở form/modal hợp lệ; chọn workspace giữ đúng ngữ cảnh khi đi tới documents/chatbots.

### Tài liệu

Toolbar gồm workspace selector, search, format filter và upload. Bảng hiển thị tên, định dạng, kích thước, trạng thái, ngày tải và actions. Các trạng thái xử lý dùng `nz-badge`/tag; retry và delete giữ hành vi/API hiện tại, có confirm cho delete.

### Chatbot và cài đặt

Chatbot dùng master-detail: danh sách trái, conversation phải; message streaming, citations, input và send state phản ánh API. Settings dùng `nz-tabs` gồm Thông tin chung, Nguồn tri thức, AI & Mô hình, Bảo mật và Nhúng mã. Embed panel cho copy-to-clipboard feedback và publish status.

## Trạng thái và lỗi

Mỗi dữ liệu bất đồng bộ có skeleton/loading rõ ràng. Lỗi API hiển thị thông báo có hành động retry nếu an toàn. Empty state nêu nguyên nhân và CTA đúng ngữ cảnh. Button submit bị disable khi form invalid hoặc request đang chạy. Sao chép embed báo thành công/thất bại bằng notification của NG-ZORRO.

## Responsive và accessibility

Desktop theo bố cục ảnh mẫu. Ở tablet sidebar co lại; ở mobile sidebar thành drawer, thanh công cụ tài liệu xuống hàng và bảng thành danh sách metadata. Tất cả icon button có `aria-label`, focus ring nhìn thấy được, thứ tự tab hợp lý và màu trạng thái không phải dấu hiệu duy nhất.

## Kiểm thử và nghiệm thu

- Unit test layout/route để xác nhận public/admin shell và redirect legacy routes.
- Unit test state loading, empty, error cho dashboard, workspace, documents và chatbots.
- Unit test thao tác tạo workspace, lọc/tìm tài liệu, upload, delete confirmation, gửi chat và copy embed.
- `npm test` và `npm run build` phải pass.
- Kiểm tra thủ công các route ở desktop và mobile, không lỗi console và không có request API sai prefix.

## Tiêu chí hoàn thành

Người dùng có thể vào landing, xác thực, dùng sidebar để đến mọi module, tạo/chọn workspace, tải và quản lý tài liệu, quản lý/chat với chatbot và sao chép mã nhúng. Giao diện có hình thức, phân cấp, spacing và màu sắc gần với mẫu được cung cấp, đồng thời tất cả thao tác tiếp tục dùng API thực của RagHub.
