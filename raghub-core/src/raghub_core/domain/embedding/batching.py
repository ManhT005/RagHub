"""Token-aware batch splitting and checkpoint resume helpers."""
from __future__ import annotations


def split_batches(
    chunk_tokens: list[int],
    *,
    max_chunks: int = 24,
    target_tokens: int = 10_000,
) -> list[tuple[int, int]]:
    """Split chunk indexes into [start, end) batches by count and token budget."""
    batches: list[tuple[int, int]] = []
    start = 0
    tokens = 0
    count = 0
    for index, size in enumerate(chunk_tokens):
        if count >= max_chunks or (tokens > 0 and tokens + size > target_tokens):
            batches.append((start, index))
            start, tokens, count = index, 0, 0
        tokens += size
        count += 1
    if count:
        batches.append((start, len(chunk_tokens)))
    return batches


def remaining_batches(total: int, completed: set[int]) -> list[int]:
    """Batch indexes still to embed; completed checkpoints are skipped."""
    return [index for index in range(total) if index not in completed]
