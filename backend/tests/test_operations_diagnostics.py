import io
import json
import logging

from app.infrastructure.telemetry.adapter import LoggingTelemetry, json_logger
from scripts.capture_rag_operations import summarize_telemetry


def test_json_telemetry_round_trip_reports_tail_latency_and_redacts_content(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(json_logger, "handlers", [logging.StreamHandler(output)])
    telemetry = LoggingTelemetry(json_logs=True)
    telemetry.timing("parse", 10, {"question": "secret-question", "kind": "upload"})
    telemetry.timing("parse", 1000, {})
    telemetry.counter("embedding_cache_hits", {}, 3)
    telemetry.counter("embedding_cache_misses", {}, 1)
    assert "secret-question" not in output.getvalue()
    report = summarize_telemetry([*output.getvalue().splitlines(), "unstructured other log"])
    assert report["stage_timings"]["parse"]["p95_ms"] == 1000
    assert report["cache_hit_rate"] == 0.75
    assert report["skipped_records"] == 1
    assert "correlation_id" not in json.dumps(report)
