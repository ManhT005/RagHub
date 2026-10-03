# RagHub — Core Isolation & Self-Hosted Operationalization Plan
## System Dev + Tech Lead Refactor Guide

**Repository:** `ManhT005/RagHub`  
**Branch baseline:** `refactor/core-selfhost-v1`  
**Reviewed HEAD:** `9e5a73ff92e924d296d315d49c1e6117a8723eea`  
**Base:** `develop @ 8c1c5ef1745167d7ce4c38bf6e50af2b68c7c868`

## 1. Mục tiêu kiến trúc

Mục tiêu không chỉ là “code sạch hơn”, mà là:

> **RagHub Core phải trở thành engine RAG độc lập, có thể được host bởi nhiều runtime khác nhau mà không sửa business logic.**

Self-host là host đầu tiên. Sau này có thể có:

```text
Self-host Console
Cloud SaaS
Private Enterprise
Headless API
CLI
Background Worker
Dedicated Public Chat Runtime
```

Tất cả đều dùng:

```text
SAME RAGHUB CORE
```

---

## 2. Kiến trúc đích

```text
                         RAGHUB CORE
                              │
              ┌───────────────┼───────────────┐
              │               │               │
          Ingestion        Retrieval       RAG Runtime
              │               │               │
              └───────────────┼───────────────┘
                              │
                            Ports
                              │
               ┌──────────────┼──────────────┐
               │              │              │
           Storage        Vector Store    AI Runtime
               │              │              │
               └──────────────┼──────────────┘
                              │
                          Composition
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
   Self-host API        Public Chat Host        Worker Host
         │                    │                    │
         └────────────────────┼────────────────────┘
                              │
                        Infrastructure
```

Core tuyệt đối không biết:

```text
FastAPI
HTTP
SSE
Celery
Redis
MinIO
Elasticsearch
SQLAlchemy
Docker
Admin UI
RBAC role name
Cloud
Self-host
Billing
Subscription
```

Core chỉ biết:

```text
Domain state
Commands
Policies
Use cases
Ports
Typed events
Errors
```

---

## 3. Đánh giá branch hiện tại

Các phần đã đúng hướng:

```text
core_domain/
application/
ports/
composition/
delivery/
infrastructure/
```

Các use case/contract quan trọng đã có:

```text
UploadDocumentUseCase
RunIngestionUseCase
BuildDocumentIndexUseCase
ReindexWorkspaceUseCase
RetrieveContextUseCase
StreamRagChatUseCase
ProviderDescriptor
typed RagEvent
CoreError
ObjectStoragePort
VectorStorePort
ProviderResolverPort
TaskQueuePort
ConversationRepositoryPort
UsageRecorderPort
```

Public Chat và Playground đã dùng chung:

```text
StreamRagChatUseCase
```

Đây là nền tảng đúng.

Các vấn đề còn lại chủ yếu nằm ở host/control-plane layer:

```text
ChatbotService -> delivery/http/sse
modules/chatbots/public_limits.py -> Redis infrastructure
modules/admin/* -> global user lifecycle
legacy services vẫn tự composition dependency
self-host composition root chưa thật sự độc lập
UI vẫn mang tư duy "admin server"
```

---

# GIAI ĐOẠN A — Khóa Core Boundary

## A1. Xóa dependency ngược `service -> delivery`

Hiện:

```text
ChatbotService
→ app.delivery.http.sse.event_payload
```

do compatibility method `stream()`.

### Fix

```text
[ ] Xóa `ChatbotService.stream()`
[ ] Chỉ giữ `stream_events()`
[ ] Chuyển caller còn dùng tuple events sang `RagEvent`
[ ] Giữ SSE mapping duy nhất trong `delivery/http/sse.py`
```

### Exit Gate

```text
modules/service không import app.delivery.*
```

---

## A2. Chuẩn hóa Core DTO

Loại compatibility dạng:

```text
RetrievedChunk ↔ dict
```

Core retrieval nên dùng typed objects:

```text
RetrievedChunk
RankedChunk
ContextChunk
IndexedChunk
DocumentIndex
```

Refactor:

```text
fuse_rrf()
build_context_bundle()
citation resolver
```

để không còn `dict[str, Any]` trong Core.

---

## A3. Async ObjectStorage Port

Hiện storage port sync trong application async.

Target:

```python
class ObjectStoragePort(Protocol):
    async def put(...)
    async def get(...)
    async def remove(...)
```

MinIO adapter chịu trách nhiệm:

```text
asyncio.to_thread(...)
```

Application không biết blocking SDK.

---

## A4. Core error taxonomy

Giữ `CoreError` transport-free.

Ổn định các code:

```text
DOCUMENT_NOT_FOUND
CHATBOT_NOT_FOUND
CHATBOT_NOT_PUBLISHED
PROVIDER_TIMEOUT
PROVIDER_UNAVAILABLE
SEARCH_UNAVAILABLE
QUEUE_UNAVAILABLE
```

HTTP layer map code → status.

CLI/worker về sau có mapper riêng.

---

# GIAI ĐOẠN B — Composition Root thật sự

## B1. Tạo Self-host Composition Root

Tạo:

```text
backend/app/composition/self_host.py
```

Concept:

```python
class SelfHostContainer:
    def upload_document(self): ...
    def retry_document(self): ...
    def run_ingestion(self): ...
    def retrieve_context(self): ...
    def stream_chat(self): ...
    def manage_chatbots(self): ...
```

Không cần DI framework.

---

## B2. Không construct adapter trong Application

Forbidden:

```text
application/
→ MinioObjectStorage()
→ ProviderResolver()
→ ElasticsearchVectorStore()
→ CeleryTaskQueue()
```

Dependencies phải được inject qua constructor.

---

## B3. Tách composition theo host

```text
composition/self_host.py
composition/public_chat.py
composition/worker.py
```

Sau này có thể thêm:

```text
composition/cloud.py
composition/cli.py
```

mà không sửa Core.

---

# GIAI ĐOẠN C — Self-host Runtime Host

Self-host phải được hiểu là:

```text
Self-host application
→ consumes RagHub Core
```

không phải:

```text
admin server + Core gắn vào
```

## C1. Boundary sản phẩm

```text
SelfHostApp
├── Authentication
├── Workspace Console
├── AI Configuration
├── Documents
├── Chatbot
├── Playground
├── Integration
└── System Health
```

Không có:

```text
Customers
Platform Admin
Billing
Plans
Customer provisioning
```

---

## C2. Organization là internal boundary

Giữ:

```text
Organization
Workspace
```

nhưng UI không expose Organization như khái niệm SaaS.

Self-host:

```text
Default Organization
└── Workspaces
```

Organization tồn tại để:

```text
isolation
ownership
future extension
```

---

## C3. Bootstrap Owner

Tạo:

```text
backend/app/cli.py
```

Command:

```bash
python -m app.cli bootstrap-owner
```

Behavior:

```text
create owner user
create default organization
create ADMIN membership
idempotent
```

Không seed test account trong production.

---

## C4. Hạ priority User Management

`/admin/users` giữ backward-compatible trong giai đoạn đầu.

UI self-host nên:

```text
hide khỏi primary navigation
```

hoặc chuyển vào:

```text
System → Users
```

User management không được định nghĩa kiến trúc product nữa.

---

# GIAI ĐOẠN D — Public Chat Host

Public Chat là một host quanh cùng RAG Core:

```text
PublicChatHost
├── Resolve Embed Key
├── Origin Policy
├── Rate Limit
├── Concurrency
├── Deadline
├── Observability
└── StreamRagChatUseCase
```

## D1. Move Redis admission

Hiện:

```text
modules/chatbots/public_limits.py
```

Target:

```text
infrastructure/redis/public_chat_admission.py
```

hoặc:

```text
delivery/public/admission.py
```

Redis không nằm trong module business.

---

## D2. Admission abstraction

Có thể thêm:

```python
class PublicChatAdmissionPort(Protocol):
    async def check_rate(...)
    async def acquire(...)
    async def release(...)
```

Redis là adapter.

RAG Core không biết admission implementation.

---

## D3. Public identity invariant

Luôn resolve server-side:

```text
embed_key
→ chatbot
→ workspace
→ organization
```

Không tin:

```text
organization_id
workspace_id
```

từ browser.

---

# GIAI ĐOẠN E — Worker Host

Worker chỉ chạy use case.

Target:

```text
Celery
→ Worker Composition
→ Use Case
```

Không:

```text
Celery
→ parse/chunk/embed/index
```

## E1. Ingestion Worker

Worker chỉ giữ:

```text
task id
distributed lock
retry scheduling
event loop bootstrap
logging
```

Business state machine nằm ở:

```text
RunIngestionUseCase
```

## E2. Reindex Worker

```text
Celery
→ ReindexWorkspaceUseCase
```

Không duplicate indexing pipeline.

---

# GIAI ĐOẠN F — Self-host Configuration Layer

Core không đọc ENV.

Host đọc ENV và inject config.

## F1. Ownership

```text
app/core/config.py
```

thuộc runtime host, không phải Core.

Architecture test tiếp tục cấm Core import `get_settings()`.

## F2. Nhóm config

```text
DatabaseSettings
StorageSettings
RedisSettings
VectorSettings
ProviderSettings
PublicChatSettings
RuntimeSettings
```

Không nhất thiết tách class ngay, nhưng `.env` và docs phải nhóm rõ.

## F3. Provider defaults

Self-host ưu tiên:

```text
Embedding = LocalSentenceTransformer
Chat = Ollama
```

External optional:

```text
Gemini
OpenAI-compatible
```

Core không biết provider default.

---

# GIAI ĐOẠN G — Self-host Infrastructure Package

Target stack:

```text
gateway
api
worker
admin-web
chat-widget
postgres
redis
elasticsearch
minio
ollama optional
```

## G1. CPU-first

Base:

```text
docker-compose.self-host.yml
```

không require NVIDIA.

GPU:

```text
docker-compose.gpu.yml
```

override riêng.

## G2. Persistent volumes

Bắt buộc:

```text
postgres
elasticsearch
minio
ollama models
```

Redis tùy policy persistence.

## G3. Exposure

Production chỉ expose:

```text
gateway
```

Không public:

```text
Postgres
Redis
MinIO
Elasticsearch
```

## G4. Secrets

Production yêu cầu:

```text
APP_SECRET_KEY
PROVIDER_MASTER_KEY
POSTGRES_PASSWORD
S3_SECRET_KEY
```

Không dùng default insecure.

---

# GIAI ĐOẠN H — Operational Readiness

Self-host phải vận hành được, không chỉ start được.

## H1. Health

```text
/health/live
/health/ready
```

Readiness:

```text
PostgreSQL
Redis
Elasticsearch
MinIO
```

AI provider readiness tách riêng.

Ollama/Gemini down không nhất thiết làm API core unhealthy.

## H2. Backup

Document:

```text
PostgreSQL dump
MinIO data
Elasticsearch strategy
APP_SECRET_KEY
PROVIDER_MASTER_KEY
```

`PROVIDER_MASTER_KEY` là critical secret.

## H3. Restore

Test thực tế:

```text
new environment
→ restore DB
→ restore storage
→ restore secrets
→ start
→ retrieval/chat PASS
```

## H4. Upgrade

```text
backup
pull images
alembic upgrade head
restart
health
smoke
```

---

# GIAI ĐOẠN I — Core Contract Tests

## I1. Pure Core

Chạy chỉ với minimal dependencies.

Test:

```text
parser
chunker
RRF
context builder
citation resolver
prompt
typed events
errors
```

Không Docker.

## I2. Fake-port E2E

Test full flow:

```text
Upload
→ Ingestion
→ Index
→ Retrieve
→ Chat
```

bằng fake ports.

Đây là bằng chứng quan trọng nhất rằng Core độc lập.

## I3. Adapter tests riêng

```text
MinIO
Elasticsearch
Redis
Celery
Provider adapters
```

không nằm trong core-only suite.

---

# GIAI ĐOẠN J — Architecture Gate

Giữ và mở rộng:

```text
backend/tests/core/test_architecture.py
```

Reject nếu:

```text
core_domain -> app.core
core_domain -> app.modules
core_domain -> infrastructure
application -> infrastructure
application -> delivery
application -> composition
ports -> infrastructure
```

Allowed:

```text
delivery -> composition/application
composition -> application + infrastructure
infrastructure -> ports/core_domain
```

---

# GIAI ĐOẠN K — Self-host E2E

Full path:

```text
Bootstrap owner
↓
Login
↓
Create workspace
↓
Configure embedding
↓
Configure chat
↓
Upload document
↓
Ingestion READY
↓
Playground
↓
Publish bot
↓
Allowed Origin
↓
Embed
↓
Public Chat
```

## Local AI release path

```text
LocalSentenceTransformer
+
Ollama
```

phải chạy không cần external API key.

External provider E2E có thể là manual/secret-backed job.

---

# GIAI ĐOẠN L — CI

Current CI giữ:

```text
core-contracts
backend
integration
frontend
widget
compose
migration
docker-images
```

Thêm:

```text
self-host-smoke
```

chạy:

```text
nightly
manual
release candidate
```

Không nhất thiết mọi PR.

Branch Core chỉ được coi merge-ready sau khi PR vào `develop` chạy full CI xanh.

---

# GIAI ĐOẠN M — Control Plane Cleanup

Chỉ làm sau khi Core + Self-host runtime ổn.

Các residue hiện tại:

```text
/admin/users
ADMIN / WORKSPACE_ADMIN
AdminLayout
Trung tâm quản trị
organization context header
global user disable
```

Chúng không còn làm bẩn Core nhưng vẫn làm product shell mang tư duy admin server.

## M1. Rename shell

```text
AdminLayout
→ ConsoleLayout
```

UI:

```text
Trung tâm quản trị
→ RagHub Console
```

## M2. Navigation

Target:

```text
Overview
Workspaces
AI Settings
System
Profile
```

Workspace:

```text
Overview
Documents
Chatbot
Playground
Integration
Settings
```

## M3. Users

Move:

```text
/app/users
```

vào:

```text
/system/users
```

hoặc hide nếu chỉ một owner.

## M4. Global disable bug

Current:

```text
organization ADMIN
→ User.status = DISABLED
```

nên tách thành:

```text
membership status
```

nếu tiếp tục support multi-user/multi-org.

Không sửa vấn đề này trong Core package.

---

# 70. Repository target

```text
backend/app/

core_domain/
application/
ports/

composition/
├── self_host.py
├── public_chat.py
└── worker.py

delivery/
├── http/
├── public/
└── workers/

infrastructure/
├── persistence/
├── object_storage/
├── vector_store/
├── providers/
├── redis/
└── queue/

modules/
├── auth/
├── users/
├── memberships/
├── workspaces/
├── documents/
├── chatbots/
└── ai_providers/
```

`modules/*` có thể tiếp tục làm compatibility/control-plane facade. Không cần move sạch ngay.

---

# 71. Thứ tự PR tiếp theo

## PR-1 — `refactor/core-clean-boundaries`

```text
remove service -> delivery dependency
typed retrieval DTO cleanup
async object storage port
architecture test expansion
```

## PR-2 — `refactor/selfhost-composition-root`

```text
SelfHostContainer
PublicChatContainer
WorkerContainer
remove legacy runtime construction khỏi services
```

## PR-3 — `refactor/public-admission-adapter`

```text
move Redis admission khỏi modules/chatbots
optional PublicChatAdmissionPort
behavior unchanged
```

## PR-4 — `feat/selfhost-bootstrap`

```text
bootstrap owner
default organization
remove production test-seed dependency
```

## PR-5 — `feat/selfhost-runtime-compose`

```text
self-host compose
CPU base
GPU override
env example
persistent volumes
gateway-only exposure
```

## PR-6 — `feat/selfhost-console`

```text
AdminLayout -> ConsoleLayout
workspace-first navigation
AI Settings
Integration
hide/deprioritize user management
```

## PR-7 — `test/selfhost-e2e`

```text
Local ST
Ollama
ingestion
RAG
public widget
restart persistence
```

## PR-8 — `ops/selfhost-release`

```text
backup
restore
upgrade
health
release docs
```

---

# 72. Definition of Done — Core Isolation

```text
[ ] core_domain imports only stdlib + approved pure libs
[ ] application imports only core_domain + ports
[ ] ports import only core_domain/stdlib
[ ] no application code constructs adapters
[ ] no HTTP status in Core
[ ] no SSE serialization in Core
[ ] no Redis/Celery/DB concept in Core
[ ] provider registry detached from ORM
[ ] public and authenticated chat share one RAG use case
[ ] ingestion/reindex share one indexing pipeline
[ ] fake-port full flow runs without Docker
```

---

# 73. Definition of Done — Self-host Operational

```text
[ ] fresh machine installs from images
[ ] bootstrap owner works
[ ] no manual DB insert
[ ] local embedding works
[ ] Ollama works
[ ] upload -> READY
[ ] retrieval works
[ ] playground works
[ ] publish works
[ ] embed works
[ ] origin validation works
[ ] public SSE works
[ ] rate limit works
[ ] concurrency cleanup works
[ ] restart preserves data
[ ] backup/restore verified
[ ] upgrade documented
```

---

# 74. Definition of Done — Future Host Ready

```text
[ ] Self-host composition outside Core
[ ] Public Chat host outside Core
[ ] Worker host outside Core
[ ] Core has no deployment-mode condition
[ ] Core has no ADMIN/WORKSPACE_ADMIN semantics
[ ] tenant/workspace scope remains generic
[ ] infrastructure adapters replaceable
```

---

# 75. Không làm lúc này

```text
Platform Admin
Cloud SaaS
Billing
Subscription
Customer onboarding
Enterprise license
SSO/SAML
Kubernetes
Helm
Microservices
```

Các phần này chỉ được mở sau:

```text
Core isolated
+
Self-host operational
```

---

# 76. Ưu tiên Tech Lead

### P0

```text
Full CI verify current refactor
remove service -> delivery dependency
composition root
self-host bootstrap
self-host compose
```

### P1

```text
public admission relocation
workspace-first console
local AI E2E
backup/restore
```

### P2

```text
control-plane role cleanup
legacy facade removal
folder cleanup
```

---

# 77. Nguyên tắc cuối cùng

RagHub phải được hiểu là:

```text
RagHub Core
=
Reusable RAG Engine
```

Self-host:

```text
RagHub Self-host
=
Core
+ Self-host Composition
+ Console
+ Infrastructure Adapters
+ Deployment
```

Cloud sau này:

```text
RagHub Cloud
=
Same Core
+ Cloud Composition
+ Cloud Control Plane
+ Managed Infrastructure
```

Nếu một runtime mới yêu cầu sửa `core_domain` hoặc business use cases chỉ vì cách deploy khác nhau, boundary vẫn chưa đạt.

Mục tiêu của roadmap này là chứng minh:

> **Core không thuộc Self-host, Cloud hay Admin Server. Core là engine độc lập; Self-host chỉ là implementation host đầu tiên của Core.**
