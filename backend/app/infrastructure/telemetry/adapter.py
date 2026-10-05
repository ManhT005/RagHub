"""Telemetry adapters: structured timing logs and test doubles.

A telemetry outage never fails chat/ingestion: every public method swallows
its own errors. Labels pass an allowlist (low-cardinality only); anything
resembling content, IDs or secrets is replaced before emission.
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping

from raghub_core.ports.telemetry import ALLOWED_LABEL_KEYS

from app.infrastructure.telemetry.correlation import correlation_id

logger = logging.getLogger("raghub.telemetry")

_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.\-:]{1,64}$")


def sanitize_labels(labels: Mapping[str, str]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for key, value in labels.items():
        if key not in ALLOWED_LABEL_KEYS:
            continue
        text = str(value)
        clean[key] = text if _SAFE_VALUE.match(text) else "other"
    return clean


class LoggingTelemetry:
    """Stage timings/counters as structured logs with correlation ID."""

    def timing(self, stage: str, duration_ms: float, labels: Mapping[str, str]) -> None:
        try:
            logger.info(
                "stage_timing",
                extra={
                    "correlation_id": correlation_id(),
                    "stage": stage,
                    "duration_ms": round(duration_ms, 2),
                    "labels": sanitize_labels(labels),
                },
            )
        except Exception:
            pass

    def counter(self, name: str, labels: Mapping[str, str], value: int = 1) -> None:
        try:
            logger.info(
                "stage_counter",
                extra={
                    "correlation_id": correlation_id(),
                    "metric": name,
                    "value": value,
                    "labels": sanitize_labels(labels),
                },
            )
        except Exception:
            pass


class InMemoryTelemetry(LoggingTelemetry):
    """Test double recording sanitized emissions."""

    def __init__(self) -> None:
        self.timings: list[tuple[str, float, dict[str, str]]] = []
        self.counters: list[tuple[str, dict[str, str], int]] = []

    def timing(self, stage: str, duration_ms: float, labels: Mapping[str, str]) -> None:
        self.timings.append((stage, duration_ms, sanitize_labels(labels)))

    def counter(self, name: str, labels: Mapping[str, str], value: int = 1) -> None:
        self.counters.append((name, sanitize_labels(labels), value))


class Timer:
    def __init__(self, telemetry, stage: str, labels: Mapping[str, str]) -> None:
        self.telemetry = telemetry
        self.stage = stage
        self.labels = labels
        self.started = 0.0

    def __enter__(self):
        self.started = time.perf_counter()
        return self

    def __exit__(self, *args):
        if self.telemetry is not None:
            self.telemetry.timing(
                self.stage, (time.perf_counter() - self.started) * 1000, self.labels
            )
        return False
