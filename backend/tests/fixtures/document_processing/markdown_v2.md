---
title: Hướng dẫn xử lý tài liệu thử nghiệm
language: vi
---

# Vận hành

## Trạng thái tài liệu

| Trạng thái | Ý nghĩa |
|---|---|
| UPLOADED | File đã được nhận |
| PARSING | Đang đọc nội dung |
| CHUNKING | Đang chia đoạn |
| EMBEDDING | Đang tạo vector |
| INDEXING | Đang lập chỉ mục |
| READY | Sẵn sàng tìm kiếm |

## Khóa cấu hình

1. Giữ APP_SECRET_KEY cho việc ký token.
   - Không đưa khóa thật vào tài liệu thử nghiệm.
2. Giữ PROVIDER_MASTER_KEY riêng để giải mã credential provider.
3. Sao lưu cả cấu hình và dữ liệu trước khi cập nhật.

```dotenv
# Đây là chuỗi mẫu, không phải credential thật.
APP_SECRET_KEY=EXAMPLE_ONLY
PROVIDER_MASTER_KEY=ANOTHER_EXAMPLE_ONLY
```

## Ví dụ mã

```python
def ready():
    # Dòng này thuộc code, không phải heading Markdown.
    return True
```
