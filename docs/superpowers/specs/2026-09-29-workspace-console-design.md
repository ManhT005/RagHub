# Workspace Console — thiết kế trải nghiệm

## Mục tiêu

Biến Admin Portal từ các trang rời (`Workspace`, `Tài liệu`, `Chatbot`) thành
một luồng vận hành RAG theo workspace:

`chọn workspace → cấu hình điều kiện còn thiếu → tải tài liệu → tài liệu READY → chat có citation`

Người dùng vận hành RagHub hằng ngày không phải nhớ trang nào tương ứng với
từng bước. Hệ thống luôn hiển thị bước tiếp theo có thể thực hiện.

## Phạm vi

- Chỉ thay đổi Angular Admin: cấu trúc route, component và giao diện.
- Giữ nguyên API và dữ liệu backend hiện có.
- Giữ theme navy/cyan/indigo đã áp dụng trên nhánh này.
- Không thay đổi cơ chế RBAC; backend vẫn là nơi quyết định quyền.

## Điều hướng

Sidebar tối giản còn ba điểm vào:

1. **Tổng quan** — các workspace và việc cần xử lý.
2. **Không gian làm việc** — Workspace Console của workspace đang chọn.
3. **Cài đặt tổ chức** — tổ chức, thành viên và cấu hình ở cấp tổ chức.

Các route `documents` và `chatbots` cũ chuyển người dùng đến Workspace Console
để không tách luồng. Nếu chưa chọn workspace, màn hình hiển thị trạng thái trống
với hành động duy nhất là tạo workspace đầu tiên.

## Workspace Console

```text
Tổ chức / Workspace                       [Tải tài liệu] [Thiết lập]
Tên workspace + trạng thái: Sẵn sàng / Cần hoàn tất

[ AI provider ] [ Tài liệu READY ] [ Chatbot publish ]

Tài liệu (40%)                             Trợ lý RAG (60%)
├─ kéo thả / chọn tệp                      ├─ trạng thái chatbot
├─ danh sách và tiến độ ingestion           ├─ hội thoại streaming
└─ retry, re-index, xóa                     ├─ citation mở nguồn
                                             └─ ô đặt câu hỏi
```

- Thanh ngữ cảnh luôn cho biết tổ chức và workspace đang hoạt động.
- Checklist sẵn sàng là điều hướng hành động: chọn mục chưa đạt sẽ mở đúng
  phần thiết lập; mục đạt dùng trạng thái rõ ràng thay vì chỉ dùng màu.
- Danh sách tài liệu có upload, tiến độ, lỗi, retry, re-index và xóa tại cùng
  một nơi. Sau upload, item xuất hiện ngay và polling hiện có tiếp tục cập nhật
  trạng thái ingestion.
- Khung chat luôn hiện. Nếu chưa đủ điều kiện, phần bảo vệ nói rõ còn thiếu gì
  và đưa người dùng đến hành động sửa; không để textarea bị vô hiệu hóa mà không
  giải thích.
- Citation vẫn dùng metadata backend trả về; bấm citation chọn/làm nổi tài liệu
  nguồn trong cột trái. Không yêu cầu API mới để thực hiện phiên bản đầu.

## Thiết lập workspace

Các thiết lập ít dùng được đưa vào panel mở từ nút **Thiết lập**:

- AI provider: chọn cấu hình Local Ollama hoặc Gemini, kiểm tra provider, gán
  embedding và chat provider cho workspace.
- Chatbot: tên, system prompt, retrieval limit, publish/unpublish.
- Triển khai: thông tin trạng thái publish; chỗ cho embed script và allowed
  origins được giữ như một vùng mở rộng khi API/UI tương ứng sẵn sàng.

Panel không che mất trạng thái tài liệu; khi lưu thành công, checklist và chat
cập nhật tại chỗ.

## Trạng thái và lỗi

| Tình huống | Hiển thị | Hành động chính |
| --- | --- | --- |
| Chưa có workspace | Trạng thái trống có mô tả ngắn | Tạo workspace đầu tiên |
| Chưa gán AI provider | Checklist “Cần thiết lập” | Mở Thiết lập AI |
| Không có tài liệu READY | Chat guard + trạng thái ingestion | Tải tài liệu / xem tiến độ |
| Chưa publish chatbot | Chat guard | Mở Thiết lập chatbot |
| Tài liệu FAILED | Lỗi cụ thể tại dòng tài liệu | Thử lại |
| Chat/provider lỗi | Thông báo theo lỗi API hiện có | Thử gửi lại / kiểm tra provider |

## Kiến trúc frontend

- Tách phần điều hướng chọn context workspace thành state dùng chung ở shell hoặc
  `WorkspaceConsoleComponent`; không nhân bản select tổ chức/workspace trong
  Documents và Chatbots.
- `WorkspaceConsoleComponent` phối hợp các thành phần tập trung trách nhiệm:
  `ReadinessChecklist`, `DocumentPanel`, `AssistantPanel`, `SetupPanel`.
- Tái sử dụng service/API và Signal state đang có của Documents/Chatbots; không
  gọi API ngoài phạm vi workspace hiện hành.
- Các component cũ có thể được dùng làm nguồn để tách dần UI; route cũ redirect
  thay vì duy trì hai luồng giao diện.

## Khả năng truy cập và responsive

- Checklist/chip có nhãn văn bản, không truyền đạt trạng thái chỉ bằng màu.
- Tất cả hành động có focus nhìn thấy được và có tên rõ ràng.
- Desktop dùng hai cột 40/60; dưới 960px xếp Tài liệu trước, Chat sau; panel
  thiết lập hiển thị toàn chiều rộng.

## Kiểm thử

- Unit test route redirect và rendering các trạng thái: không có workspace,
  thiếu provider, không có tài liệu READY, chatbot chưa publish, sẵn sàng chat.
- Unit test hành động citation chọn đúng tài liệu nguồn khi metadata tồn tại.
- Regression test app shell vẫn gắn `design-system-dark`.
- Chạy Angular test và production build sau khi triển khai.

## Tiêu chí nghiệm thu

1. Người dùng có thể hoàn thành luồng workspace → upload → READY → publish →
   chat mà không cần tự đổi giữa trang Tài liệu và Chatbot.
2. Mọi điều kiện chặn chat đều chỉ ra lý do và hành động tiếp theo.
3. Tiến độ/lỗi ingestion có thể xử lý ngay trên console.
4. Chat và citation vẫn dùng đúng API hiện có, không lẫn dữ liệu workspace.
5. Giao diện hoạt động được ở desktop và mobile, giữ theme dark hiện tại.
