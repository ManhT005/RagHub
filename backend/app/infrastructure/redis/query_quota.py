from redis.asyncio import Redis

from app.infrastructure.redis.quota_buckets import QuotaBucketStore


class QueryQuota:
    """Reserve full shared capacity for interactive queries, leaving background its cap."""
    def __init__(self, settings):
        self.settings = settings

    async def acquire(self, *, scope, tokens, background=False):
        redis = Redis.from_url(self.settings.redis_url, socket_timeout=2)
        try:
            await QuotaBucketStore(redis, self.settings).acquire(
                scope=scope, tokens=tokens, background=False
            )
        finally:
            await redis.aclose()
