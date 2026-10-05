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


# Declarative registry: context windows come from provider profiles, never
# guessed from model names at runtime. Unknown models use the conservative
# fallback below (flagged, safety factor applied).
MODEL_PROFILES: dict[str, ModelProfile] = {
    "gemini-2.5-flash": ModelProfile("gemini-2.5-flash", 1_048_576),
    "gemini-2.5-pro": ModelProfile("gemini-2.5-pro", 1_048_576),
    "gemini-3.5-flash-lite": ModelProfile("gemini-3.5-flash-lite", 1_048_576),
    "gpt-4o-mini": ModelProfile("gpt-4o-mini", 128_000, exact_tokenizer=True),
    "gpt-4o": ModelProfile("gpt-4o", 128_000, exact_tokenizer=True),
}

FALLBACK_CONTEXT_WINDOW = 8_192


@dataclass(frozen=True)
class ResolvedProfile:
    profile: ModelProfile
    fallback_used: bool


def resolve_profile(model: str) -> ResolvedProfile:
    name = (model or "").strip()
    profile = MODEL_PROFILES.get(name)
    if profile is not None:
        return ResolvedProfile(profile, fallback_used=False)
    return ResolvedProfile(ModelProfile(name, FALLBACK_CONTEXT_WINDOW), fallback_used=True)


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
