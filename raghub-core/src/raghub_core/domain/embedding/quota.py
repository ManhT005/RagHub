"""Quota profiles and rolling-bucket decisions for shared provider pools.

Pure logic: the Redis adapter implements the same windows against Redis TIME.
The host supplies provider quota profiles.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuotaProfile:
    rpm: int
    tpm: int
    rpd: int


@dataclass(frozen=True)
class QuotaConfig:
    quota: QuotaProfile
    background: QuotaProfile


TOKEN_SAFETY_FACTOR = 1.2


def estimate_tokens(total_chars: int) -> int:
    """Conservative token estimate when no exact tokenizer is available."""
    return max(1, int(total_chars / 4 * TOKEN_SAFETY_FACTOR))


def retry_after_delay(
    *,
    retry_after_seconds: float | None,
    attempt: int,
    base_seconds: float = 1.0,
    max_seconds: float = 60.0,
    jitter_ratio: float = 0.25,
) -> float:
    """Honor Retry-After; otherwise exponential backoff with deterministic jitter."""
    if retry_after_seconds is not None and retry_after_seconds >= 0:
        return min(retry_after_seconds, max_seconds)
    jitter = 1.0 + jitter_ratio * ((attempt % 5) / 4 - 0.5) * 2
    return min(max_seconds, base_seconds * (2**attempt) * jitter)


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    wait_seconds: float
    available_at_ms: int


class RollingQuotaBucket:
    """In-memory rolling window bucket (reference for the Redis implementation)."""

    def __init__(self, profile: QuotaProfile) -> None:
        self.profile = profile
        self.minute_marks: list[tuple[int, int]] = []
        self.day_marks: list[tuple[int, int]] = []

    def acquire(self, *, now_ms: int, tokens: int) -> QuotaDecision:
        minute_ago = now_ms - 60_000
        day_ago = now_ms - 86_400_000
        self.minute_marks = [(t, n) for t, n in self.minute_marks if t > minute_ago]
        self.day_marks = [(t, n) for t, n in self.day_marks if t > day_ago]
        minute_reqs = len(self.minute_marks)
        minute_tokens = sum(n for _, n in self.minute_marks)
        day_reqs = len(self.day_marks)
        waits: list[int] = []
        if minute_reqs + 1 > self.profile.rpm:
            waits.append(self.minute_marks[0][0] + 60_000 - now_ms)
        if minute_tokens + tokens > self.profile.tpm:
            waits.append(self.minute_marks[0][0] + 60_000 - now_ms if self.minute_marks else 60_000)
        if day_reqs + 1 > self.profile.rpd:
            waits.append(
                self.day_marks[0][0] + 86_400_000 - now_ms if self.day_marks else 86_400_000
            )
        if waits:
            wait_ms = max(0, max(waits))
            return QuotaDecision(False, wait_ms / 1000, now_ms + wait_ms)
        self.minute_marks.append((now_ms, tokens))
        self.day_marks.append((now_ms, tokens))
        return QuotaDecision(True, 0.0, now_ms)
