from raghub_core.domain.rag.model_profile import ModelProfile, ResolvedProfile

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


def resolve_profile(model: str, *, context_window: int | None = None) -> ResolvedProfile:
    name = (model or "").strip()
    profile = ModelProfile(name, context_window) if context_window else MODEL_PROFILES.get(name)
    if profile is not None:
        return ResolvedProfile(profile, fallback_used=False)
    return ResolvedProfile(ModelProfile(name, FALLBACK_CONTEXT_WINDOW), fallback_used=True)
