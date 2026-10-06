"""Telemetry port: stage timings and low-cardinality counters.

Implementations must never raise and never record content: no question,
answer, context, chunk excerpt, prompt or secret appears in logs, metric
labels or keys. Correlation IDs travel in log records only, never labels.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

ALLOWED_LABEL_KEYS = frozenset(
    {"provider", "model", "parser", "stage", "outcome", "config_version", "kind", "band", "status"}
)


class TelemetryPort(Protocol):
    def timing(self, stage: str, duration_ms: float, labels: Mapping[str, str]) -> None:
        ...

    def counter(self, name: str, labels: Mapping[str, str], value: int = 1) -> None:
        ...


class NoOpTelemetry:
    def timing(self, stage: str, duration_ms: float, labels: Mapping[str, str]) -> None:
        return None

    def counter(self, name: str, labels: Mapping[str, str], value: int = 1) -> None:
        return None
