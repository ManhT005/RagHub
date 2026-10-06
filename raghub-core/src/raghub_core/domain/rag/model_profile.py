"""Model context windows and token counting for the global prompt budget.

Exact counts use the bundled tiktoken encoding (cl100k). For providers whose
tokenizer differs, the fallback estimator applies a 1.2 safety factor and the
run is flagged so telemetry can track tokenizer mismatch.
"""
from __future__ import annotations

from dataclasses import dataclass

from raghub_core.domain.ingestion.tokenizer import ENCODING

TOKEN_SAFETY_FACTOR = 1.2


@dataclass(frozen=True)
class ModelProfile:
    model: str
    context_window: int
    exact_tokenizer: bool = False


@dataclass(frozen=True)
class ResolvedProfile:
    profile: ModelProfile
    fallback_used: bool


def count_tokens_exact(text: str) -> int:
    return len(ENCODING.encode(text or ""))


def count_tokens_fallback(text: str) -> int:
    return max(1, int(len(text or "") / 4 * TOKEN_SAFETY_FACTOR))


def validate_budget_config(
    *, context_window: int, max_output_tokens: int, safety_margin: int
) -> int:
    """Fail fast on invalid config; return the usable input budget."""
    budget = context_window - max_output_tokens - safety_margin
    if max_output_tokens < 1 or safety_margin < 0:
        raise ValueError("Invalid prompt budget configuration.")
    if budget <= 0:
        raise ValueError("Model context window is smaller than output plus safety margin.")
    return budget
