"""Quota-aware resumable embedding: scheduler, buckets, batches, checkpoints."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from raghub_core.application.ingestion.build_document_index import BuildDocumentIndexUseCase
from raghub_core.domain.embedding.batching import remaining_batches, split_batches
from raghub_core.domain.embedding.quota import (
    RollingQuotaBucket,
    estimate_tokens,
    retry_after_delay,
)
from raghub_core.domain.embedding.scheduler import WorkItemRef, pick_order
from raghub_core.ports.embedding_quota import (
    QuotaBackendUnavailableError,
    QuotaDepletedError,
)

from app.modules.ai_providers.quota_profiles import GEMINI_EMBEDDING
from app.modules.ai_providers.work_items import (
    WAITING_QUOTA,
    WorkItemProcessor,
    decode_artifact,
    decode_manifest,
    encode_artifact,
    encode_manifest,
)


def _ref(workspace: str, kind: str = "upload") -> WorkItemRef:
    return WorkItemRef(uuid4(), uuid4() if workspace == "*" else workspace_ids[workspace], kind)


workspace_ids = {}


def _ws(name: str):
    workspace_ids.setdefault(name, uuid4())
    return name


def test_weighted_round_robin_cycles_workspaces():
    items = [_ref(_ws("a")), _ref(_ws("b")), _ref(_ws("c")), _ref(_ws("a"))]
    order = pick_order(items)
    workspaces = []
    lookup = {item.id: item.workspace_id for item in items}
    for item_id in order:
        if lookup[item_id] not in workspaces:
            workspaces.append(lookup[item_id])
    assert workspaces == [workspace_ids["a"], workspace_ids["b"], workspace_ids["c"]]
    assert len(order) == 4


def test_query_priority_beats_upload_flood():
    flood = [_ref(_ws("flood")) for _ in range(10)]
    urgent = _ref(_ws("user"), kind="query")
    order = pick_order([*flood, urgent])
    assert order[0] == urgent.id
    reindex = _ref(_ws("re"), kind="reindex")
    order = pick_order([reindex, *flood])
    assert order[-1] == reindex.id


def test_quota_bucket_blocks_rpm_tpm_rpd():
    bucket = RollingQuotaBucket(GEMINI_EMBEDDING.background)
    now = 1_000_000
    for _ in range(80):
        assert bucket.acquire(now_ms=now, tokens=10).allowed
    decision = bucket.acquire(now_ms=now, tokens=10)
    assert not decision.allowed and decision.available_at_ms > now
    assert decision.wait_seconds > 0


def test_quota_bucket_tpm_window():
    bucket = RollingQuotaBucket(GEMINI_EMBEDDING.background)
    now = 2_000_000
    assert bucket.acquire(now_ms=now, tokens=20_000).allowed
    assert not bucket.acquire(now_ms=now, tokens=2_000).allowed
    later = bucket.acquire(now_ms=now + 61_000, tokens=2_000)
    assert later.allowed


def test_retry_after_and_backoff():
    assert retry_after_delay(retry_after_seconds=5, attempt=3) == 5
    first = retry_after_delay(retry_after_seconds=None, attempt=0)
    second = retry_after_delay(retry_after_seconds=None, attempt=1)
    assert 0 < first <= 60 and first < second
    assert estimate_tokens(400) >= 100


def test_split_batches_respects_count_and_tokens():
    batches = split_batches([500] * 50, max_chunks=24, target_tokens=10_000)
    assert batches[0] == (0, 20)
    assert all(end - start <= 24 for start, end in batches)
    assert remaining_batches(3, {0, 2}) == [1]
    assert remaining_batches(2, {0, 1}) == []


def test_manifest_and_artifact_roundtrip():
    chunks = [{"id": "c0", "tokens": 12, "text": "hello"}]
    assert decode_manifest(encode_manifest(chunks)) == chunks
    assert decode_artifact(encode_artifact([[1.0, 2.0]])) == [[1.0, 2.0]]


class FakeRepo:
    """In-memory stand-in for WorkItemRepository (same method surface)."""

    def __init__(self) -> None:
        self.items = {}
        self.checkpoints = {}
        self.quota_waits = []

    async def claim(self, item_id):
        return self.items.get(item_id)

    async def pool_scope(self, item):
        return "gemini:model:proj"

    async def completed_batches(self, item_id):
        return set(self.checkpoints.get(item_id, {}))

    async def record_batch(self, item, *, batch, start, end, artifact):
        self.checkpoints.setdefault(item.id, {})[batch] = artifact
        item.embedded_chunks = end

    async def wait_quota(self, item, available_at_ms):

        item.state = WAITING_QUOTA
        item.available_at = datetime.fromtimestamp(available_at_ms / 1000, tz=UTC)
        self.quota_waits.append(item.id)

    async def complete(self, item):
        item.state = "COMPLETED"

    async def fail(self, item, code, message):
        item.state = "FAILED"
        item.error = code

    async def checkpoint_artifact(self, item_id, batch):
        return self.checkpoints.get(item_id, {}).get(batch)


def _processor(repo, **overrides):
    blobs = overrides.pop("blobs", {})
    calls = {"embed": 0, "finalized": []}

    async def load_blob(key):
        return blobs[key]

    async def store_blob(key, blob):
        blobs[key] = blob

    async def embed_texts(texts):
        calls["embed"] += 1
        if overrides.get("fail_embed"):
            from raghub_core.domain.providers.errors import ProviderRateLimitError

            raise ProviderRateLimitError("429")
        return [[float(len(t)), 0.0] for t in texts]

    async def finalize(item_id, vectors):
        calls["finalized"].append((item_id, len(vectors)))

    quota = overrides.get("quota")

    class AllowAll:
        async def acquire(self, *, scope, tokens, background=True):
            return None

    return (
        WorkItemProcessor(
            repo,
            quota or AllowAll(),
            load_blob=load_blob,
            store_blob=store_blob,
            embed_texts=embed_texts,
            finalize=finalize,
            max_chunks=overrides.get("max_chunks", 24),
            target_tokens=overrides.get("target_tokens", 10_000),
            dimension=2,
        ),
        blobs,
        calls,
    )


def _manifest(n: int) -> bytes:
    return encode_manifest([{"id": f"c{i}", "tokens": 10, "text": f"chunk {i}"} for i in range(n)])


async def test_processor_embeds_one_batch_then_resumes_without_duplicates():
    from types import SimpleNamespace

    repo = FakeRepo()
    item_id = uuid4()
    item = SimpleNamespace(
        id=item_id,
        organization_id=uuid4(),
        workspace_id=uuid4(),
        manifest_key="manifest",
        total_chunks=30,
        embedded_chunks=0,
        state="RUNNING",
    )
    repo.items[item_id] = item
    processor, blobs, calls = _processor(repo, max_chunks=24)
    blobs["manifest"] = _manifest(30)

    first = await processor.process_one(item_id)
    assert first.done is False and item.embedded_chunks == 24 and calls["embed"] == 1
    second = await processor.process_one(item_id)
    assert second.done is True and item.embedded_chunks == 30 and calls["embed"] == 2
    assert calls["finalized"] == [(item_id, 30)]


async def test_processor_skips_checkpointed_batches_after_crash():
    from types import SimpleNamespace

    repo = FakeRepo()
    item_id = uuid4()
    item = SimpleNamespace(
        id=item_id,
        organization_id=uuid4(),
        workspace_id=uuid4(),
        manifest_key="manifest",
        total_chunks=30,
        embedded_chunks=24,
        state="RUNNING",
    )
    repo.items[item_id] = item
    repo.checkpoints[item_id] = {0: "artifact://batch0"}
    processor, blobs, calls = _processor(repo, max_chunks=24)
    blobs["manifest"] = _manifest(30)
    blobs["artifact://batch0"] = encode_artifact([[1.0, 0.0]] * 24)

    outcome = await processor.process_one(item_id)
    assert outcome.done is True and calls["embed"] == 1  # only batch 1 re-embedded
    assert calls["finalized"] == [(item_id, 30)]


async def test_processor_waits_on_quota_without_calling_provider():
    from types import SimpleNamespace

    repo = FakeRepo()
    item_id = uuid4()
    item = SimpleNamespace(
        id=item_id,
        organization_id=uuid4(),
        workspace_id=uuid4(),
        manifest_key="manifest",
        total_chunks=5,
        embedded_chunks=0,
        state="RUNNING",
    )
    repo.items[item_id] = item

    class DenyAll:
        async def acquire(self, *, scope, tokens, background=True):
            raise QuotaDepletedError(12.0, 9_999_999_999)

    processor, blobs, calls = _processor(repo, quota=DenyAll())
    blobs["manifest"] = _manifest(5)

    outcome = await processor.process_one(item_id)
    assert outcome.done is False and calls["embed"] == 0
    assert repo.items[item_id].state == WAITING_QUOTA
    assert repo.quota_waits == [item_id]


async def test_build_use_case_fails_closed_without_provider_call():
    from uuid import uuid4

    from raghub_core.api import RetrievalScope
    from raghub_core.domain.ingestion.errors import IngestionError
    from raghub_core.domain.ingestion.models import IngestionDocument
    from raghub_core.domain.ingestion.parser import ParsedSection

    from tests.core.fakes import FakeProviderResolver, FakeVectorStore

    providers, store = FakeProviderResolver(), FakeVectorStore()
    use_case = BuildDocumentIndexUseCase(
        storage=FakeStorage(),
        parser=lambda data, name: [ParsedSection("hello world " * 50, name, 0)],
    )

    async def down(tokens: int) -> None:
        raise QuotaBackendUnavailableError("redis down")

    scope = RetrievalScope(uuid4(), uuid4())
    document = IngestionDocument(
        scope=scope,
        document_id=uuid4(),
        version_id=uuid4(),
        storage_key="k",
        source_name="doc.md",
    )
    with pytest.raises(IngestionError) as exc:
        await use_case.execute(
            document,
            lambda: providers.resolve_embedding(scope),
            lambda runtime: store,
            acquire_quota=down,
        )
    assert exc.value.code == "EMBEDDING_QUOTA_UNAVAILABLE" and exc.value.retryable
    assert providers.embedding.calls == []


class FakeStorage:
    async def get(self, key: str) -> bytes:
        return b"# hello"

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        pass

    async def remove(self, key: str) -> None:
        pass


def test_progress_fields_are_additive_nullable():
    from app.modules.documents.schemas import DocumentAccepted, DocumentResponse

    assert DocumentResponse.model_fields["embedded_chunks"].is_required() is False
    assert DocumentResponse.model_fields["total_chunks"].is_required() is False
    assert DocumentResponse.model_fields["queue_position"].is_required() is False
    assert set(DocumentAccepted.model_fields) == {
        "document_id",
        "document_version_id",
        "job_id",
        "status",
        "created_at",
    }


def test_queue_caps_use_settings():
    from app.core.config import Settings
    settings = Settings(provider_pool_max_active_jobs_per_workspace=2,
                        provider_pool_max_pending_jobs_per_workspace=7)
    assert settings.provider_pool_max_active_jobs_per_workspace == 2
    assert settings.provider_pool_max_pending_jobs_per_workspace == 7


def test_migration_chain_is_linked():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).parent.parent
        / "alembic"
        / "versions"
        / "20261005_0022_embedding_work_items.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0022", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "20261005_0022"
    assert migration.down_revision == "20261005_0021"


async def test_builder_quota_port_waits_instead_of_hammering():
    from uuid import uuid4

    from raghub_core.api import RetrievalScope
    from raghub_core.domain.ingestion.errors import IngestionError
    from raghub_core.domain.ingestion.models import IngestionDocument
    from raghub_core.domain.ingestion.parser import ParsedSection
    from raghub_core.ports.embedding_quota import QuotaDepletedError
    from raghub_core.ports.provider_resolver import EmbeddingRuntime

    from tests.core.fakes import FakeProviderResolver, FakeVectorStore

    providers = FakeProviderResolver()
    use_case = BuildDocumentIndexUseCase(
        storage=FakeStorage(),
        parser=lambda data, name: [ParsedSection("hello world " * 50, name, 0)],
        quota=_ScriptedQuota([QuotaDepletedError(5.0, 123)]),
    )
    scope = RetrievalScope(uuid4(), uuid4())

    async def resolve():
        runtime = await providers.resolve_embedding(scope)
        return EmbeddingRuntime(runtime.provider, runtime.index_name, runtime.dimension,
                                quota_scope="gemini:m:proj")

    document = IngestionDocument(scope=scope, document_id=uuid4(), version_id=uuid4(),
                                 storage_key="k", source_name="doc.md")
    with pytest.raises(IngestionError) as exc:
        await use_case.execute(document, resolve, lambda runtime: FakeVectorStore())
    assert exc.value.code == "EMBEDDING_QUOTA_WAIT" and exc.value.retryable
    assert providers.embedding.calls == []


async def test_builder_quota_port_skipped_without_scope():
    from uuid import uuid4

    from raghub_core.api import RetrievalScope
    from raghub_core.domain.ingestion.models import IngestionDocument
    from raghub_core.domain.ingestion.parser import ParsedSection

    from tests.core.fakes import FakeProviderResolver, FakeVectorStore

    providers = FakeProviderResolver()
    providers.embedding.vectors = [[1.0, 0.0]]
    use_case = BuildDocumentIndexUseCase(
        storage=FakeStorage(),
        parser=lambda data, name: [ParsedSection("hello world " * 50, name, 0)],
        quota=_ScriptedQuota([]),
    )
    scope = RetrievalScope(uuid4(), uuid4())
    document = IngestionDocument(scope=scope, document_id=uuid4(), version_id=uuid4(),
                                 storage_key="k", source_name="doc.md")

    class NoScopeStore(FakeVectorStore):
        def replace(self, index):
            pass

    await use_case.execute(
        document,
        lambda: providers.resolve_embedding(scope),
        lambda runtime: NoScopeStore(),
    )
    assert providers.embedding.calls  # embedded without quota (no pool scope)


class _ScriptedQuota:
    def __init__(self, effects):
        self.effects = list(effects)
        self.calls = []

    async def acquire(self, *, scope, tokens, background=True):
        self.calls.append((scope, tokens))
        if self.effects:
            raise self.effects.pop(0)


def test_retry_after_parsing_and_gemini_stride():
    import httpx

    from app.modules.ai_providers.adapters.google_gemini import GoogleGeminiEmbeddingProvider
    from app.modules.ai_providers.adapters.openai_compatible import (
        OpenAICompatibleEmbeddingProvider,
        _retry_after_seconds,
    )

    response = httpx.Response(429, headers={"retry-after": "7"})
    assert _retry_after_seconds(response) == 7.0
    assert _retry_after_seconds(httpx.Response(429, headers={})) == 0.0
    assert _retry_after_seconds(httpx.Response(429, headers={"retry-after": "999"})) == 60.0
    assert GoogleGeminiEmbeddingProvider.batch_stride == 24
    assert OpenAICompatibleEmbeddingProvider.batch_stride == 64
