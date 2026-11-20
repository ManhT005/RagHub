# Bật reranking local

Overlay `infrastructure/docker-compose.reranking.yml` bật cross-encoder đã có
trong RagHub: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, revision pin trong
`app.infrastructure.ai.local_reranker`. Đây là cấu hình thử nghiệm, chưa phải
cam kết tăng điểm chất lượng hoặc đạt SLO CPU.

## Chuẩn bị model (không đổi dữ liệu)

Cần image backend **local-ai**, dung lượng trống và Internet để tải model một
lần. Dùng đúng tên project `raghub-selfhost` để giữ cache và dữ liệu hiện tại.
Nếu deployment dùng tên khác, thay `-p` nhất quán trong các lệnh dưới đây.
Không chạy preparation đồng thời với API đã bật reranking.

```sh
# Chỉ định image local-ai đã có trên máy, ví dụ image backend đang deploy:
export RAGHUB_RERANKER_IMAGE=raghub-selfhost/backend:develop-71daa3e
docker compose --env-file .env.self-host -p raghub-selfhost \
  -f infrastructure/docker-compose.reranker-prepare.yml run --rm reranker-prepare
```

Lệnh in `RAG_RERANKER_EXPECTED_SHA256`. Lưu đúng giá trị đó vào
`.env.self-host`. Không commit file env hoặc token. Runtime xác minh checksum
trước khi load model; API không tự tải model.

## Bật cho deployment build cục bộ

Sau khi build image mới có `rerank_start`, chạy:

```sh
docker compose --env-file .env.self-host -p raghub-selfhost \
  -f infrastructure/docker-compose.self-host.yml \
  -f infrastructure/docker-compose.self-host.build.yml \
  -f infrastructure/docker-compose.reranking.yml \
  up -d --wait api
```

Deployment GHCR bỏ file `.build.yml`, chọn backend suffix `-local-ai` và tag đã
publish có module startup mới. API warm model trước khi serve; thiếu extras,
snapshot hoặc sai checksum khiến startup fail rõ ràng thay vì âm thầm fallback
mọi câu hỏi. Reranking giới hạn 12 candidates → 5 kết quả, timeout 10s; có thể
override bằng biến môi trường. Tắt adaptive để lần thử đầu không skip inference.
Workspace đã bind rerank provider riêng vẫn có ưu tiên theo cơ chế hiện có.

Các lần Compose tiếp theo cần tiếp tục có file overlay để giữ tính năng bật.
Không thay embedding/index hay yêu cầu reindex. Khi model runtime timeout/busy,
retrieval fallback về hybrid theo cơ chế hiện có. Chưa đo cải thiện benchmark;
dùng cùng bộ câu hỏi và index để so sánh trước/sau, gồm cả p95 latency.

## Rollback

Chạy lại `up -d --wait api` với cùng project/env và hai file Compose gốc, bỏ
overlay reranking. Các cờ runtime quay lại giá trị trong env/preset gốc; bảo đảm
`RAG_RERANKER_ENABLED` không được đặt `true` trong env khi rollback. Không xóa
volume hoặc đổi database. File snapshot có thể giữ trong cache để dùng lại.
