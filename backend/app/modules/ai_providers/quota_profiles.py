from raghub_core.domain.embedding.quota import QuotaConfig, QuotaProfile

GEMINI_EMBEDDING = QuotaConfig(
    quota=QuotaProfile(rpm=100, tpm=30_000, rpd=1_000),
    background=QuotaProfile(rpm=80, tpm=21_000, rpd=900),
)

