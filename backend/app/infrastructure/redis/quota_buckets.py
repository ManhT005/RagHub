"""Shared Redis rolling quota buckets. Keys carry pool scope only, never content."""

from raghub_core.domain.embedding.quota import GEMINI_EMBEDDING, QuotaProfile
from raghub_core.ports.embedding_quota import (
    QuotaBackendUnavailableError,
    QuotaDepletedError,
)
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings

# Atomic across replicas: prune windows, check RPM/TPM/RPD, reserve one slot.
# Returns 0 when reserved, otherwise wait milliseconds until capacity frees.
ACQUIRE_SCRIPT = """
local clock = redis.call('TIME')
local now_ms = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local rpm_key, tpm_key, rpd_key = KEYS[1], KEYS[2], KEYS[3]
local rpm = tonumber(ARGV[1])
local tpm = tonumber(ARGV[2])
local rpd = tonumber(ARGV[3])
local tokens = tonumber(ARGV[4])
local member = ARGV[5]
redis.call('ZREMRANGEBYSCORE', rpm_key, '-inf', now_ms - 60000)
redis.call('ZREMRANGEBYSCORE', tpm_key, '-inf', now_ms - 60000)
redis.call('ZREMRANGEBYSCORE', rpd_key, '-inf', now_ms - 86400000)
local waits = {}
if redis.call('ZCARD', rpm_key) + 1 > rpm then
    local oldest = redis.call('ZRANGE', rpm_key, 0, 0, 'WITHSCORES')
    table.insert(waits, tonumber(oldest[2]) + 60000 - now_ms)
end
local used_tokens = 0
for _, m in ipairs(redis.call('ZRANGE', tpm_key, 0, -1)) do
    local sep = string.find(m, ':')
    used_tokens = used_tokens + tonumber(string.sub(m, 1, sep - 1))
end
if used_tokens + tokens > tpm then
    local oldest = redis.call('ZRANGE', tpm_key, 0, 0, 'WITHSCORES')
    local base = #oldest > 0 and tonumber(oldest[2]) or now_ms
    table.insert(waits, base + 60000 - now_ms)
end
if redis.call('ZCARD', rpd_key) + 1 > rpd then
    local oldest = redis.call('ZRANGE', rpd_key, 0, 0, 'WITHSCORES')
    local base = #oldest > 0 and tonumber(oldest[2]) or now_ms
    table.insert(waits, base + 86400000 - now_ms)
end
if #waits > 0 then
    local wait = waits[1]
    for i = 2, #waits do wait = math.max(wait, waits[i]) end
    return math.max(wait, 1)
end
redis.call('ZADD', rpm_key, now_ms, member)
redis.call('ZADD', tpm_key, now_ms, tokens .. ':' .. member)
redis.call('ZADD', rpd_key, now_ms, member)
redis.call('EXPIRE', rpm_key, 70)
redis.call('EXPIRE', tpm_key, 70)
redis.call('EXPIRE', rpd_key, 86410)
return 0
"""


class QuotaBucketStore:
    """Rolling RPM/TPM/RPD buckets keyed by pool quota scope."""

    def __init__(self, redis: Redis, settings: Settings | None = None) -> None:
        self.redis = redis
        self.settings = settings

    @staticmethod
    def profile(background: bool = True) -> QuotaProfile:
        return GEMINI_EMBEDDING.background if background else GEMINI_EMBEDDING.quota

    def _limits(self, background: bool) -> QuotaProfile:
        if self.settings is None:
            return self.profile(background)
        if background:
            return QuotaProfile(
                rpm=self.settings.gemini_embedding_ingestion_rpm,
                tpm=self.settings.gemini_embedding_ingestion_tpm,
                rpd=self.settings.gemini_embedding_ingestion_rpd,
            )
        return QuotaProfile(rpm=100, tpm=30_000, rpd=1_000)

    async def acquire(self, *, scope: str, tokens: int, background: bool = True) -> None:
        """Reserve quota or raise; Redis failure raises fail-closed, never allows blind."""
        import time
        import uuid

        profile = self._limits(background)
        keys = [f"quota:{scope}:rpm", f"quota:{scope}:tpm", f"quota:{scope}:rpd"]
        try:
            wait_ms = await self.redis.eval(
                ACQUIRE_SCRIPT,
                3,
                *keys,
                profile.rpm,
                profile.tpm,
                profile.rpd,
                max(1, tokens),
                f"{time.time_ns()}:{uuid.uuid4().hex}",
            )
        except RedisError as exc:
            raise QuotaBackendUnavailableError("Quota coordinator unreachable.") from exc
        if int(wait_ms) > 0:
            wait_seconds = int(wait_ms) / 1000
            raise QuotaDepletedError(
                wait_seconds, int(time.time() * 1000) + int(wait_ms)
            )
