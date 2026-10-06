"""Correlation IDs across FastAPI, use cases, tasks and workers."""
from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

_correlation: ContextVar[str] = ContextVar("raghub_correlation_id", default="")


def correlation_id() -> str:
    return _correlation.get() or "uncorrelated"


def use_correlation_id(value: str | None = None) -> str:
    token = (value or "").strip()[:128] or str(uuid4())
    _correlation.set(token)
    return token
