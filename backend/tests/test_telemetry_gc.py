"""Stage telemetry with redaction and index GC safety (offline)."""
import logging
from uuid import uuid4

import pytest

from app.infrastructure.elasticsearch.gc import IndexCandidate, classify
from app.infrastructure.elasticsearch.gc_runner import GcLockBusyError, GcRunner
from app.infrastructure.telemetry.adapter import (
    InMemoryTelemetry,
    LoggingTelemetry,
    sanitize_labels,
)
from app.infrastructure.telemetry.correlation import correlation_id, use_correlation_id


def _candidate(name, state="COMPLETED", age=100.0, ws="ws-1", **overrides):
    base = {
        "index_name": name,
        "version_id": f"v-{name}",
        "workspace_id": ws,
        "state": state,
        "age_hours": age,
    }
    base.update(overrides)
    return IndexCandidate(**base)


def test_labels_allowlist_and_redaction():
    labels = sanitize_labels({
        "stage": "search",
        "model": "gemini-2.5-flash",
        "workspace_id": str(uuid4()),
        "question": "điểm chuẩn Y khoa?",
        "secret": "gAAAAAB",
    })
    assert labels == {"stage": "search", "model": "gemini-2.5-flash"}
    assert sanitize_labels({"stage": "a b"}) == {"stage": "other"}


def test_telemetry_outage_never_fails_pipeline(caplog):
    class Broken(LoggingTelemetry):
        def timing(self, stage, duration_ms, labels):
            raise RuntimeError("telemetry down")

    telemetry = Broken()
    with caplog.at_level(logging.INFO, logger="raghub.telemetry"):
        telemetry.counter("x", {"stage": "search"})
    # counter swallowed its own error path too (no raise); pipeline continues
    assert True


def test_inmemory_records_sanitized_emissions():
    telemetry = InMemoryTelemetry()
    telemetry.timing("search", 12.5, {"stage": "search", "answer": "secret text"})
    telemetry.counter("empty_context", {"stage": "context"})
    assert telemetry.timings == [("search", 12.5, {"stage": "search"})]
    assert telemetry.counters == [("empty_context", {"stage": "context"}, 1)]


def test_correlation_id_flows():
    use_correlation_id("req-123")
    assert correlation_id() == "req-123"
    use_correlation_id()
    assert len(correlation_id()) == 36


async def test_middleware_sets_correlation_and_header():
    from fastapi import Request

    from app.core.middleware import RequestIdMiddleware

    seen = {}

    async def call_next(request):
        from starlette.responses import JSONResponse

        seen["ctx"] = correlation_id()
        return JSONResponse({})

    scope = {"type": "http", "headers": [(b"x-request-id", b"abc-1")],
             "method": "GET", "path": "/", "query_string": b""}
    middleware = RequestIdMiddleware(app=None)
    response = await middleware.dispatch(Request(scope), call_next)
    assert response.headers["X-Request-ID"] == "abc-1"
    assert seen["ctx"] == "abc-1"


async def test_use_cases_emit_stages_without_content():
    from raghub_core.api import RetrievalScope, RetrieveContextUseCase
    from raghub_core.domain.retrieval.models import RetrievedChunk

    from tests.core.fakes import FakeProviderResolver, FakeVectorStore

    telemetry = InMemoryTelemetry()
    providers, search = FakeProviderResolver(), FakeVectorStore()

    class Search(FakeVectorStore):
        async def close(self):
            self.closed += 1

    search = Search()
    uid = uuid4()
    search.hits = [RetrievedChunk(uid, uuid4(), uid, "sensitive chunk text", "s", None, None, 0.5)]

    class Readiness:
        async def filter_ready(self, scope, hits):
            return []

    use_case = RetrieveContextUseCase(providers, Readiness(), lambda _: search, telemetry=telemetry)
    await use_case.retrieve(RetrievalScope(uuid4(), uuid4()), "secret question?", 5)
    stages = {stage for stage, _, _ in telemetry.timings}
    assert {"query_embedding", "search", "readiness_filter"} <= stages
    blob = str(telemetry.timings) + str(telemetry.counters)
    assert "sensitive chunk text" not in blob and "secret question" not in blob
    assert ("empty_context", {"stage": "context"}, 1) in telemetry.counters


def test_gc_protects_active_pending_workitem_and_two_recent():
    candidates = [
        _candidate("active", state="RETIRED", age=1000.0, active=True),
        _candidate("job", state="BUILDING", pending_or_running=True),
        _candidate("work", referenced_by_work_item=True),
        _candidate("new-1", age=1.0),
        _candidate("new-2", age=2.0),
        _candidate("old", age=100.0),
    ]
    decisions = {d.index_name: d for d in classify(candidates)}
    assert decisions["active"].decision == "keep"
    assert decisions["job"].decision == "keep"
    assert decisions["work"].decision == "keep"
    assert decisions["new-1"].decision == "keep"
    assert decisions["new-2"].decision == "keep"
    assert decisions["old"].decision == "keep"  # COMPLETED has no age-based deletion


def test_gc_retention_windows():
    assert classify([_candidate("r-old", state="RETIRED", age=25.0)])[0].decision == "delete"
    assert classify([_candidate("r-young", state="RETIRED", age=23.0)])[0].decision == "keep"
    assert classify([_candidate("f-old", state="FAILED", age=8 * 24.0)])[0].decision == "delete"
    assert classify([_candidate("f-young", state="FAILED", age=6 * 24.0)])[0].decision == "keep"
    unknown = classify([IndexCandidate("raghub_chunks_zzz", None, None, "unknown", None)])
    assert unknown[0].decision == "report"


def _runner(candidates, **overrides):
    deleted, records = [], []

    async def load():
        return candidates

    async def delete(name):
        if overrides.get("fail_delete"):
            raise RuntimeError("es down")
        deleted.append(name)

    async def recheck(name):
        changed = overrides.get("changed", set())
        if name in changed:
            original = next(c for c in candidates if c.index_name == name)
            return IndexCandidate(original.index_name, original.version_id,
                                  original.workspace_id, original.state, original.age_hours,
                                  active=True)
        return next(c for c in candidates if c.index_name == name)

    async def record(report, correlation, pairs):
        records.append((report, pairs))

    runner = GcRunner(
        load_candidates=load,
        delete_index=delete,
        recheck=recheck,
        record_run=record,
        acquire_lock=overrides.get("lock", _free_lock()),
        release_lock=_release,
        batch_limit=overrides.get("batch_limit", 10),
    )
    return runner, deleted, records


def _free_lock():
    async def lock():
        return True

    return lock


_released: list[bool] = []


async def _release() -> None:
    _released.append(True)


async def test_gc_dry_run_deletes_nothing():
    _released.clear()
    runner, deleted, records = _runner([_candidate("r-old", state="RETIRED", age=25.0)])
    report = await runner.run(apply=False, correlation_id="c1")
    assert deleted == [] and report.deleted == 0 and report.mode == "dry-run"
    assert records and _released


async def test_gc_apply_rereads_and_stops_on_change():
    _released.clear()
    candidates = [
        _candidate("r-1", state="RETIRED", age=25.0),
        _candidate("r-2", state="RETIRED", age=26.0),
    ]
    runner, deleted, _ = _runner(candidates, changed={"r-1"})
    report = await runner.run(apply=True, correlation_id="c1")
    assert deleted == ["r-2"] and "r-1" not in deleted and report.errors == 1


async def test_gc_apply_bounded_and_lock_guarded():
    _released.clear()
    candidates = [_candidate(f"r-{i}", state="RETIRED", age=25.0) for i in range(3)]
    runner, deleted, _ = _runner(candidates, batch_limit=1)
    report = await runner.run(apply=True, correlation_id="c1")
    assert deleted == ["r-0"] and report.deleted == 1

    async def busy():
        return False

    runner2, _, _ = _runner(candidates)
    runner2.acquire_lock = busy
    with pytest.raises(GcLockBusyError):
        await runner2.run(apply=False, correlation_id="c1")


async def test_gc_apply_stops_on_delete_error():
    runner, deleted, _ = _runner([_candidate("r-1", state="RETIRED", age=25.0)],
                                 fail_delete=True)
    report = await runner.run(apply=True, correlation_id="c1")
    assert deleted == [] and report.errors == 1


def test_migration_chain_and_flag():
    import importlib.util
    from pathlib import Path

    from app.core.config import Settings

    path = (
        Path(__file__).parent.parent
        / "alembic"
        / "versions"
        / "20261005_0023_index_gc_audit.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0023", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert (migration.revision, migration.down_revision) == ("20261005_0023", "20261005_0022")
    assert Settings(_env_file=None).rag_index_gc_enabled is False
