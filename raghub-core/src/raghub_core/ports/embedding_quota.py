"""Quota coordination port: every external embedding call goes through acquire first."""
from __future__ import annotations

from typing import Protocol


class QuotaDepletedError(Exception):
    def __init__(self, wait_seconds: float, available_at_ms: int) -> None:
        self.wait_seconds = wait_seconds
        self.available_at_ms = available_at_ms
        super().__init__(f"Quota depleted; retry after {wait_seconds:.1f}s.")


class QuotaBackendUnavailableError(Exception):
    """Redis/coordinator unreachable: callers must fail closed, never call blind."""


class EmbeddingQuotaPort(Protocol):
    async def acquire(self, *, scope: str, tokens: int, background: bool = True) -> None:
        """Reserve quota or raise QuotaDepletedError / QuotaBackendUnavailableError."""
        ...
